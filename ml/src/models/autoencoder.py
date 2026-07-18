"""Module 2 — Keras autoencoder anomaly detector on raw telemetry.

Idea: train a small dense autoencoder to reconstruct NORMAL machine behaviour
(14 days x 14 sensors, z-scored per machine). Machines drifting away from their
own normal reconstruct badly -> high reconstruction error = anomaly score.
Unsupervised: labels are used ONLY to (a) keep clearly pre-failure windows out
of the training set and (b) evaluate honestly against the same 7-day labels
the supervised model uses.

Outputs:
  data/app/anomaly_scores.parquet   (machine_id, date, split, label, anomaly_score)
  data/app/anomaly_metrics.json     (PR-AUC vs baselines, config)

Run:  PYTHONPATH=src .venv/bin/python src/models/autoencoder.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ML = Path(__file__).resolve().parents[2]
WINDOW = 14          # days of telemetry per sample
TRAIN_CUTOFF = "2025-09-01"   # per-machine z-score stats come from before this date
SEED = 7

rng = np.random.default_rng(SEED)


def build_daily_matrix() -> tuple[pd.DataFrame, list[str]]:
    """Telemetry -> wide daily frame (machine x day x 14 sensor columns), z-scored
    per (machine, sensor) with TRAIN-period stats; missing -> 0 (= 'at its mean')."""
    tel = pd.read_parquet(ML / "data" / "raw" / "telemetry")
    sensors = sorted(tel["sensor"].unique())

    wide = tel.pivot_table(index=["machine_id", "date"], columns="sensor",
                           values="value", aggfunc="mean")

    train_mask = wide.index.get_level_values("date") < pd.Timestamp(TRAIN_CUTOFF)
    stats = wide[train_mask].groupby("machine_id").agg(["mean", "std"])

    z = pd.DataFrame(index=wide.index, columns=sensors, dtype="float32")
    for s in sensors:
        m = stats[(s, "mean")].reindex(wide.index.get_level_values("machine_id")).to_numpy()
        sd = stats[(s, "std")].reindex(wide.index.get_level_values("machine_id")).to_numpy()
        z[s] = (wide[s].to_numpy() - m) / np.where(sd > 0, sd, 1.0)

    z = z.clip(-6, 6).fillna(0.0)   # clip wild spikes, absent sensor/day -> 0
    return z, sensors


def build_windows(z: pd.DataFrame, sensors: list[str]) -> pd.DataFrame:
    """One flattened WINDOW x n_sensors vector per (machine, scoring Monday)."""
    scores = pd.read_parquet(ML / "data" / "app" / "scores.parquet")[
        ["machine_id", "date", "split", "label", "days_to_failure"]]

    rows, vecs = [], []
    for mid, grp in z.groupby(level="machine_id"):
        g = grp.droplevel("machine_id")
        full = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="D")).fillna(0.0)
        arr = full.to_numpy(dtype="float32")
        dates = full.index
        pos = {d: i for i, d in enumerate(dates)}
        for d in scores.loc[scores["machine_id"] == mid, "date"]:
            i = pos.get(d)
            if i is None or i + 1 < WINDOW:
                continue
            vecs.append(arr[i + 1 - WINDOW: i + 1].ravel())
            rows.append((mid, d))

    X = np.stack(vecs)
    meta = pd.DataFrame(rows, columns=["machine_id", "date"]).merge(
        scores, on=["machine_id", "date"], how="left")
    return meta, X


def train_autoencoder(X_train: np.ndarray) -> "keras.Model":
    import keras
    from keras import layers

    keras.utils.set_random_seed(SEED)
    dim = X_train.shape[1]
    model = keras.Sequential([
        layers.Input(shape=(dim,)),
        layers.Dense(64, activation="relu"),
        layers.Dense(16, activation="relu"),      # the bottleneck: 196 -> 16 numbers
        layers.Dense(64, activation="relu"),
        layers.Dense(dim, activation="linear"),
    ])
    model.compile(optimizer="adam", loss="mse")
    model.fit(X_train, X_train,                    # target = input: learn to reconstruct
              epochs=40, batch_size=256, validation_split=0.1, verbose=2,
              callbacks=[keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True)])
    return model


def prep() -> None:
    """Stage 1 (pandas only, no TF): build windows and cache them to disk."""
    print("1/2 building z-scored daily matrix from telemetry ...")
    z, sensors = build_daily_matrix()
    print(f"    {z.shape[0]:,} machine-days x {len(sensors)} sensors")

    print("2/2 building windows ...")
    meta, X = build_windows(z, sensors)
    np.savez_compressed(ML / "data" / "app" / "ae_windows.npz", X=X)
    meta.to_parquet(ML / "data" / "app" / "ae_meta.parquet", index=False)
    print(f"cached {X.shape[0]:,} windows of {WINDOW}d x {len(sensors)} sensors = {X.shape[1]} dims")


def main() -> None:
    """Stage 2 (fast, TF): load cached windows, train, evaluate, export."""
    from sklearn.metrics import average_precision_score

    X = np.load(ML / "data" / "app" / "ae_windows.npz")["X"]
    meta = pd.read_parquet(ML / "data" / "app" / "ae_meta.parquet")
    print(f"loaded {X.shape[0]:,} cached windows ({X.shape[1]} dims)")

    # train ONLY on clearly-healthy train-split windows (no imminent failure)
    healthy = (meta["split"] == "train") & (meta["label"] == 0) & (
        meta["days_to_failure"].isna() | (meta["days_to_failure"] > WINDOW))
    print(f"training autoencoder on {healthy.sum():,} healthy train windows ...")
    model = train_autoencoder(X[healthy.to_numpy()])

    print("scoring all windows ...")
    recon = model.predict(X, batch_size=1024, verbose=0)
    meta["anomaly_score"] = ((X - recon) ** 2).mean(axis=1)

    test = meta[meta["split"] == "test"]
    ae_ap = average_precision_score(test["label"], test["anomaly_score"])

    base = json.load(open(ML / "data" / "app" / "metrics.json"))
    comparison = {
        "prauc::Autoencoder (Keras, reconstruction error)": round(float(ae_ap), 4),
        "prauc::Rolling z-score alarm": base["prauc::Rolling z-score alarm"],
        "prauc::IsolationForest": base["prauc::IsolationForest"],
        "prauc::XGBoost (calibrated, supervised)": base["prauc::XGBoost (calibrated)"],
        "prevalence_test": base["prevalence_test"],
    }

    meta.drop(columns=["days_to_failure"]).to_parquet(ML / "data" / "app" / "anomaly_scores.parquet", index=False)
    out = {
        "config": {"window_days": WINDOW, "sensors": len(sensors), "input_dim": int(X.shape[1]),
                   "architecture": "196-64-16-64-196 dense, MSE", "train_windows": int(healthy.sum()),
                   "normalisation": "per-machine per-sensor z-score (train-period stats), clip +/-6",
                   "training_data": "healthy train-split windows only (no failure within 14d)"},
        "metrics": comparison,
    }
    (ML / "data" / "app" / "anomaly_metrics.json").write_text(json.dumps(out, indent=2))

    print("\n=== Module 2 — autoencoder vs baselines (test PR-AUC) ===")
    for k, v in comparison.items():
        print(f"  {k:<48} {v}")
    print("\nwrote data/app/anomaly_scores.parquet + anomaly_metrics.json")


if __name__ == "__main__":
    import sys
    if "--prep" in sys.argv:
        prep()
    else:
        main()
