"""P4 — the hybrid model: XGBoost alerts (7/14d) + XGBoost-AFT survival (30/90/180d).

Assembles a training set from weekly as-of snapshots over history, trains the two
model families with a time-based split, reports honest metrics, then scores a
schedule of as-of dates into `predictions`. The 5-horizon vector per machine is
composed short-from-classifiers / long-from-survival and clamped monotone
non-decreasing (a coherent survival curve: P7 ≤ P14 ≤ P30 ≤ P90 ≤ P180).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

from pipeline.features_live import (
    compute_panel, feature_columns, features_asof, label_within, load_frames)
from sim.common import ROOT

SHORT_HORIZONS = (7, 14)
LONG_HORIZONS = (30, 90, 180)
ALL_HORIZONS = SHORT_HORIZONS + LONG_HORIZONS
AFT_SIGMA = 1.0
MODEL_PATH = ROOT / "data/app/live_model.pkl"  # ROOT is the ml/ directory


# --------------------------------------------------------------------------- #
# Training-set assembly
# --------------------------------------------------------------------------- #
def as_of_grid(panel: pd.DataFrame, freq: str = "W", tail_daily: int = 30) -> list[pd.Timestamp]:
    """Weekly as-of dates across history + daily for the most recent `tail_daily`."""
    dmin, dmax = panel["date"].min(), panel["date"].max()
    weekly = list(pd.date_range(dmin + pd.Timedelta(days=35), dmax, freq=freq))
    daily = list(pd.date_range(dmax - pd.Timedelta(days=tail_daily), dmax, freq="D"))
    return sorted(set(weekly) | set(daily))


def assemble(panel, failures, dates, feat_cols) -> pd.DataFrame:
    """Stack per-(machine, as_of) feature rows + labels for every horizon +
    survival target (time-to-next-failure, censored)."""
    last_data = panel["date"].max()
    rows = []
    for as_of in dates:
        f = features_asof(panel, as_of)
        if f.empty:
            continue
        mids = f["machine_id"].tolist()
        for h in ALL_HORIZONS:
            f[f"y{h}"] = label_within(failures, as_of, h, mids).values
        # survival target
        nf = failures[failures.failure_date > as_of]
        nxt = nf.sort_values("failure_date").groupby("machine_id")["failure_date"].first()
        t, event = [], []
        for m in mids:
            if m in nxt.index:
                t.append(max(1, (nxt[m] - as_of).days)); event.append(1)
            else:
                t.append(max(1, (last_data - as_of).days)); event.append(0)
        f["surv_t"] = t
        f["surv_event"] = event
        rows.append(f)
    data = pd.concat(rows, ignore_index=True)
    for c in feat_cols:
        if c in data:
            data[c] = pd.to_numeric(data[c], errors="coerce")
    return data


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def _train_classifier(Xtr, ytr, Xva, yva):
    pos = max(1, int(ytr.sum())); neg = len(ytr) - pos
    clf = xgb.XGBClassifier(
        n_estimators=350, max_depth=4, learning_rate=0.05, subsample=0.8,
        colsample_bytree=0.8, min_child_weight=5, reg_lambda=2.0,
        scale_pos_weight=neg / pos, eval_metric="aucpr", n_jobs=-1, tree_method="hist")
    clf.fit(Xtr, ytr)
    # Platt calibration on validation
    raw = clf.predict_proba(Xva)[:, 1].reshape(-1, 1)
    platt = LogisticRegression(max_iter=1000)
    if len(np.unique(yva)) > 1:
        platt.fit(raw, yva)
    else:
        platt = None
    return clf, platt


def _calibrate(clf, platt, X):
    raw = clf.predict_proba(X)[:, 1]
    if platt is None:
        return raw
    return platt.predict_proba(raw.reshape(-1, 1))[:, 1]


def _train_aft(Xtr, t, event):
    d = xgb.DMatrix(Xtr)
    lower = t.astype(float)
    upper = np.where(event == 1, t, np.inf).astype(float)
    d.set_float_info("label_lower_bound", lower)
    d.set_float_info("label_upper_bound", upper)
    params = {"objective": "survival:aft", "eval_metric": "aft-nloglik",
              "aft_loss_distribution": "normal", "aft_loss_distribution_scale": AFT_SIGMA,
              "max_depth": 4, "eta": 0.05, "subsample": 0.8, "colsample_bytree": 0.8,
              "lambda": 2.0, "min_child_weight": 5, "tree_method": "hist"}
    return xgb.train(params, d, num_boost_round=300)


def _aft_prob(aft, X, horizon):
    mu = np.log(np.clip(aft.predict(xgb.DMatrix(X)), 1e-6, None))
    return norm.cdf((np.log(horizon) - mu) / AFT_SIGMA)


def compose_probs(bundle: dict, X: pd.DataFrame) -> np.ndarray:
    """5-horizon monotone survival curve per row: XGBoost short + AFT long."""
    probs = {}
    for h in SHORT_HORIZONS:
        probs[h] = _calibrate(bundle["models"][h], bundle["platts"][h], X)
    for h in LONG_HORIZONS:
        probs[h] = _aft_prob(bundle["aft"], X.values, h)
    P = np.vstack([probs[h] for h in ALL_HORIZONS]).T
    return np.maximum.accumulate(np.clip(P, 0, 1), axis=1)


def save_bundle(bundle: dict, path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: bundle[k] for k in ("models", "platts", "aft", "feat_cols", "metrics")}
    with open(path, "wb") as f:
        pickle.dump(keep, f)


def load_bundle(path: Path = MODEL_PATH) -> dict:
    with open(path, "rb") as f:
        return pickle.load(f)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def train_and_score(engine, up_to=None, write=True, model_version="v-current",
                    save_model=True) -> dict:
    from db.io import insert_rows
    frames = load_frames(engine, up_to=up_to)
    panel = compute_panel(frames)
    feat_cols = [c for c in feature_columns(panel) if not c.startswith(("y", "surv_"))]

    dates = as_of_grid(panel)
    data = assemble(panel, frames["failures"], dates, feat_cols)
    data = data.replace([np.inf, -np.inf], np.nan)

    # time-based split for honest metrics
    cut = data["as_of_date"].quantile(0.8)
    tr, va = data[data.as_of_date <= cut], data[data.as_of_date > cut]
    Xtr, Xva = tr[feat_cols], va[feat_cols]

    models, platts, metrics = {}, {}, {}
    for h in SHORT_HORIZONS:
        clf, platt = _train_classifier(Xtr, tr[f"y{h}"].values, Xva, va[f"y{h}"].values)
        models[h], platts[h] = clf, platt
        p = _calibrate(clf, platt, Xva)
        metrics[f"pr_auc_{h}d"] = float(average_precision_score(va[f"y{h}"], p)) \
            if va[f"y{h}"].sum() else None
    metrics["prevalence_7d"] = float(data["y7"].mean())

    # precision/recall @20 for the 7d model on the validation window (per as-of week)
    metrics.update(_worklist_metrics(va, _calibrate(models[7], platts[7], Xva), k=20))

    aft = _train_aft(Xtr.values, tr["surv_t"].values, tr["surv_event"].values)
    bundle = {"models": models, "platts": platts, "aft": aft, "feat_cols": feat_cols, "metrics": metrics}
    if save_model:
        save_bundle(bundle)

    scored = 0
    if write:
        score_dates = [d for d in dates if (up_to is None or d <= pd.Timestamp(up_to))]
        for as_of in score_dates:
            f = features_asof(panel, as_of)
            if f.empty:
                continue
            X = f[feat_cols].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
            P = compose_probs(bundle, X)
            rows = []
            for i, mid in enumerate(f["machine_id"].values):
                for j, h in enumerate(ALL_HORIZONS):
                    rows.append((mid, as_of.date(), int(h), float(P[i, j]), model_version))
            scored += insert_rows(engine, "predictions",
                                  ["machine_id", "as_of_date", "horizon_days", "p_fail",
                                   "model_version"], rows, page_size=5000)

    metrics["n_features"] = len(feat_cols)
    metrics["n_train_samples"] = int(len(tr))
    metrics["predictions_written"] = scored
    return {"metrics": metrics, "feat_cols": feat_cols,
            "models": models, "platts": platts, "aft": aft, "panel": panel}


def _worklist_metrics(va, p7, k=20):
    va = va.copy(); va["p"] = p7
    precs, recs = [], []
    for _, g in va.groupby("as_of_date"):
        if g["y7"].sum() == 0:
            continue
        top = g.nlargest(min(k, len(g)), "p")
        precs.append(top["y7"].sum() / len(top))
        recs.append(top["y7"].sum() / g["y7"].sum())
    return {"precision_at_20": float(np.mean(precs)) if precs else None,
            "recall_at_20": float(np.mean(recs)) if recs else None}


if __name__ == "__main__":
    from db.engine import get_engine
    out = train_and_score(get_engine(), model_version="v-current")
    print(json.dumps(out["metrics"], indent=2))
