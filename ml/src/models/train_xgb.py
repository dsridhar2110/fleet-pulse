"""Train the 7-day failure-risk classifier.

Choices worth defending:
- XGBoost on tabular features: few hundred positives, mixed feature types,
  native missing-value handling (modalities have disjoint sensor sets, so
  most sensor columns are legitimately absent for any given machine), and
  SHAP explainability for service engineers. Deep learning earns nothing here.
- Time-based split (train Jan-Aug, val Sep-Oct, test Nov-Dec): deployment
  scores the future with a model trained on the past; evaluation must too.
  We also train a deliberately-wrong RANDOM-split variant purely to report
  how much it inflates metrics (docs/case_study.md).
- Isotonic calibration on the validation window: risk scores become dispatch
  decisions and cost estimates — a 0.6 must mean 60%.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data" / "app"  # artifacts consumed by the dashboard
ART.mkdir(parents=True, exist_ok=True)

# Columns that must NEVER become features (evaluation-only / identifiers /
# post-hoc). tests/test_no_leakage.py asserts this list stays intact.
FORBIDDEN = {
    "label", "split", "days_to_failure", "next_failure_date", "component",
    "sudden", "machine_id", "date",
}
CATEGORICAL = ["modality", "model", "country"]


def load() -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_parquet(ROOT / "data/features/labeled.parquet")
    df["date"] = pd.to_datetime(df["date"])
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    feature_cols = [c for c in df.columns if c not in FORBIDDEN]
    return df, feature_cols


def fit(train: pd.DataFrame, val: pd.DataFrame, feature_cols: list[str]) -> xgb.XGBClassifier:
    pos_weight = (train.label == 0).sum() / max(1, (train.label == 1).sum())
    model = xgb.XGBClassifier(
        n_estimators=600,
        learning_rate=0.03,
        max_depth=4,
        min_child_weight=4,
        subsample=0.8,
        colsample_bytree=0.7,
        scale_pos_weight=pos_weight,
        enable_categorical=True,
        eval_metric="aucpr",
        early_stopping_rounds=50,
        tree_method="hist",
        random_state=42,
    )
    model.fit(
        train[feature_cols], train.label,
        eval_set=[(val[feature_cols], val.label)],
        verbose=False,
    )
    return model


def main() -> None:
    df, feature_cols = load()
    train = df[df.split == "train"]
    val = df[df.split == "val"]
    test = df[df.split == "test"]

    # ---- The real model: time-based split ----
    model = fit(train, val, feature_cols)

    # Calibrate on validation scores. Platt (sigmoid) scaling, not isotonic:
    # with only ~50 validation positives, isotonic overfits into coarse step
    # plateaus (risk scores pile up on a few values like 0.64 / 1.00), which
    # both misleads and looks fake. A 2-parameter logistic map stays smooth.
    val_raw = model.predict_proba(val[feature_cols])[:, 1]
    calibrator = LogisticRegression(C=1e6)
    calibrator.fit(val_raw.reshape(-1, 1), val.label)

    def calibrate(p: np.ndarray) -> np.ndarray:
        return calibrator.predict_proba(p.reshape(-1, 1))[:, 1]

    for split_df, name in [(val, "val"), (test, "test")]:
        raw = model.predict_proba(split_df[feature_cols])[:, 1]
        print(f"{name}: PR-AUC={average_precision_score(split_df.label, raw):.3f} "
              f"(prevalence {split_df.label.mean():.3%})")

    # ---- The deliberately-wrong comparison: random split, same pipeline ----
    rnd_train, rnd_test = train_test_split(df, test_size=0.2, random_state=42, stratify=df.label)
    rnd_tr, rnd_val = train_test_split(rnd_train, test_size=0.15, random_state=42,
                                       stratify=rnd_train.label)
    rnd_model = fit(rnd_tr, rnd_val, feature_cols)
    rnd_scores = rnd_model.predict_proba(rnd_test[feature_cols])[:, 1]
    rnd_prauc = average_precision_score(rnd_test.label, rnd_scores)
    print(f"random-split PR-AUC (inflated, for the case study): {rnd_prauc:.3f}")

    # ---- Persist artifacts ----
    model.save_model(ART / "xgb_model.json")

    scores = df[["machine_id", "date", "split", "label", "days_to_failure"]].copy()
    raw_all = model.predict_proba(df[feature_cols])[:, 1]
    scores["risk_raw"] = raw_all
    scores["risk_calibrated"] = calibrate(raw_all)
    scores.to_parquet(ART / "scores.parquet", index=False)

    meta = {
        "feature_cols": feature_cols,
        "best_iteration": int(model.best_iteration),
        "random_split_prauc": float(rnd_prauc),
        "calibration": "platt",
        "platt_coef": float(calibrator.coef_[0][0]),
        "platt_intercept": float(calibrator.intercept_[0]),
    }
    (ART / "model_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"artifacts -> {ART}")


if __name__ == "__main__":
    main()
