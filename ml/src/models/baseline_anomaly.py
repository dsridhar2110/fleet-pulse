"""Baselines the XGBoost model must beat to earn its complexity.

1. rank-by-age      — if ML can't beat "visit the oldest machines", stop.
2. rolling z-score  — the classic alarm rule an engineer would write first:
                      max |z| of any sensor's 7d mean vs its 90d history.
                      Proxy here: warn_burst_ratio + max slope deviation.
3. IsolationForest  — unsupervised anomaly score on the same features.

All three are scored on the SAME test rows and evaluated with the SAME
precision@k lens as the classifier (see evaluate.py).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data" / "app"


def main() -> None:
    df = pd.read_parquet(ROOT / "data/features/labeled.parquet")
    df["date"] = pd.to_datetime(df["date"])

    out = df[["machine_id", "date", "split", "label"]].copy()

    # 1. Age ranking.
    out["score_age"] = df["age_years"]

    # 2. Z-score-style drift alarm: combine warning bursts with the strongest
    # normalized 7d-vs-30d mean shift across whichever sensors the machine has.
    mean7 = df[[c for c in df.columns if c.endswith("_mean_7d")]]
    mean30 = df[[c for c in df.columns if c.endswith("_mean_30d")]].to_numpy()
    std30 = df[[c for c in df.columns if c.endswith("_std_30d")]].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.abs((mean7.to_numpy() - mean30) / np.where(std30 > 0, std30, np.nan))
    out["score_zscore"] = np.nanmax(z, axis=1) + df["warn_burst_ratio"].fillna(0)

    # 3. IsolationForest on numeric features (fit on train period only —
    # unsupervised, but it still must not see the future).
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in {"label", "days_to_failure"}
    ]
    X = df[num_cols].fillna(0.0)
    iso = IsolationForest(n_estimators=200, random_state=42, contamination="auto")
    iso.fit(X[df.split == "train"])
    out["score_iforest"] = -iso.score_samples(X)  # higher = more anomalous

    out.to_parquet(ART / "baseline_scores.parquet", index=False)
    print(f"baseline scores -> {ART}/baseline_scores.parquet")


if __name__ == "__main__":
    main()
