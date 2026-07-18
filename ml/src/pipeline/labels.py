"""Leakage-safe label construction.

Label definition: for a scoring date t, y = 1 iff the machine has a failure
in the OPEN-CLOSED interval (t, t+7]. Features (built in features_spark.py)
use data <= t only. The failure day itself — with its critical-code burst,
downtime, and post-hoc ticket text — can never appear in a feature window
for a positive label, because the failure lies strictly AFTER t.

Also attaches `days_to_failure` (for lead-time analysis, evaluation only —
NEVER a model feature) and the time-based split assignment:
    train: Jan-Aug | val: Sep-Oct | test: Nov-Dec
A random split would let the model memorize machine trajectories across
weeks; the time split simulates deployment: score the future with a model
trained on the past.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HORIZON_DAYS = 7

SPLITS = {
    "train": ("2025-01-01", "2025-08-31"),
    "val": ("2025-09-01", "2025-10-31"),
    "test": ("2025-11-01", "2025-12-31"),
}


def main() -> None:
    features = pd.read_parquet(ROOT / "data/features/feature_table.parquet")
    failures = pd.read_parquet(ROOT / "data/raw/failures.parquet")

    features["date"] = pd.to_datetime(features["date"])
    failures["failure_date"] = pd.to_datetime(failures["failure_date"])

    # For every scoring row, find the machine's NEXT failure strictly after t.
    f = failures[["machine_id", "failure_date", "component", "sudden"]].sort_values("failure_date")
    x = features[["machine_id", "date"]].sort_values("date")
    merged = pd.merge_asof(
        x,
        f.rename(columns={"failure_date": "next_failure_date"}),
        left_on="date",
        right_on="next_failure_date",
        by="machine_id",
        direction="forward",
        allow_exact_matches=False,  # failure ON the scoring date is not "future"
    )
    merged["days_to_failure"] = (merged["next_failure_date"] - merged["date"]).dt.days
    merged["label"] = (
        merged["days_to_failure"].notna() & (merged["days_to_failure"] <= HORIZON_DAYS)
    ).astype(int)

    out = features.merge(
        merged[["machine_id", "date", "label", "days_to_failure", "next_failure_date",
                "component", "sudden"]],
        on=["machine_id", "date"],
        how="left",
    )

    out["split"] = "train"
    for name, (lo, hi) in SPLITS.items():
        mask = (out["date"] >= lo) & (out["date"] <= hi)
        out.loc[mask, "split"] = name

    out.to_parquet(ROOT / "data/features/labeled.parquet", index=False)

    stats = out.groupby("split")["label"].agg(["count", "sum", "mean"])
    print(stats.rename(columns={"count": "rows", "sum": "positives", "mean": "pos_rate"}))
    print(f"\nlabeled table -> data/features/labeled.parquet ({len(out):,} rows)")


if __name__ == "__main__":
    main()
