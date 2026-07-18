"""Evaluation the way the service organization would consume it.

Framing: the model's job is a WEEKLY WORKLIST — "which k machines should a
regional team proactively inspect" — at an acceptable false-alarm cost.

Artifacts written to docs/img/ (case study) and data/app/ (dashboard):
- PR curves, model vs baselines            (pr_curves.png)
- precision@k / recall@k sweep             (precision_at_k.png)
- calibration curve + Brier score          (calibration.png)
- expected-cost vs threshold + sensitivity (cost_threshold.png)
- lead-time histogram for true positives   (lead_time.png)
- headline metrics table                   (data/app/metrics.json)
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data" / "app"
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

# Cost assumptions (order-of-magnitude, disclosed in the case study):
# proactive inspection visit ~$800; unplanned downtime ~3 days x ~$27k/day
# of lost scan revenue + patient backlog. Ratio swept in the sensitivity band.
COST_VISIT = 800
COST_MISSED = 80_000


def weekly_precision_at_k(df: pd.DataFrame, score_col: str, k: int) -> tuple[float, float]:
    """Precision/recall of the top-k worklist, averaged over scoring weeks."""
    precs, recs = [], []
    for _, week in df.groupby("date"):
        top = week.nlargest(k, score_col)
        tp = top["label"].sum()
        precs.append(tp / k)
        pos = week["label"].sum()
        if pos > 0:
            recs.append(tp / pos)
    return float(np.mean(precs)), float(np.mean(recs)) if recs else 0.0


def main() -> None:
    scores = pd.read_parquet(ART / "scores.parquet")
    base = pd.read_parquet(ART / "baseline_scores.parquet")
    df = scores.merge(
        base[["machine_id", "date", "score_age", "score_zscore", "score_iforest"]],
        on=["machine_id", "date"],
    )
    test = df[df.split == "test"].copy()

    contenders = {
        "XGBoost (calibrated)": "risk_calibrated",
        "Rolling z-score alarm": "score_zscore",
        "IsolationForest": "score_iforest",
        "Rank by machine age": "score_age",
    }

    # ---- PR curves ----
    plt.figure(figsize=(8, 6))
    metrics: dict = {"prevalence_test": float(test.label.mean())}
    for name, col in contenders.items():
        prauc = average_precision_score(test.label, test[col])
        metrics[f"prauc::{name}"] = round(float(prauc), 4)
        p, r, _ = precision_recall_curve(test.label, test[col])
        plt.plot(r, p, label=f"{name} (PR-AUC {prauc:.3f})")
    plt.axhline(test.label.mean(), color="gray", ls=":", label=f"random ({test.label.mean():.3f})")
    plt.xlabel("Recall"); plt.ylabel("Precision")
    plt.title("Test window (Nov-Dec): precision-recall, model vs baselines")
    plt.legend(); plt.tight_layout(); plt.savefig(IMG / "pr_curves.png", dpi=120); plt.close()
    metrics["rocauc::XGBoost"] = round(float(roc_auc_score(test.label, test.risk_calibrated)), 4)

    # ---- precision@k sweep ----
    ks = [5, 10, 20, 50]
    plt.figure(figsize=(8, 5))
    for name, col in contenders.items():
        pk = [weekly_precision_at_k(test, col, k)[0] for k in ks]
        plt.plot(ks, pk, marker="o", label=name)
    p20, r20 = weekly_precision_at_k(test, "risk_calibrated", 20)
    metrics["precision_at_20"] = round(p20, 4)
    metrics["recall_at_20"] = round(r20, 4)
    plt.xlabel("k = weekly proactive inspections across the fleet")
    plt.ylabel("precision@k (averaged over weeks)")
    plt.title("If the service org can visit k machines a week, how many visits pay off?")
    plt.legend(); plt.tight_layout(); plt.savefig(IMG / "precision_at_k.png", dpi=120); plt.close()

    # ---- Calibration ----
    bins = np.linspace(0, test.risk_calibrated.max() + 1e-9, 8)
    test["bin"] = pd.cut(test.risk_calibrated, bins, include_lowest=True)
    grp = test.groupby("bin", observed=True).agg(pred=("risk_calibrated", "mean"), obs=("label", "mean"), n=("label", "size"))
    plt.figure(figsize=(6.5, 6))
    plt.plot(grp.pred, grp.obs, marker="o", label="calibrated model")
    lim = max(grp.pred.max(), grp.obs.max()) * 1.1
    plt.plot([0, lim], [0, lim], "k--", lw=1, label="perfect calibration")
    brier = brier_score_loss(test.label, test.risk_calibrated)
    metrics["brier"] = round(float(brier), 5)
    plt.xlabel("mean predicted risk"); plt.ylabel("observed failure rate")
    plt.title(f"Calibration on test (Brier {brier:.4f}) — a 0.6 must mean 60%")
    plt.legend(); plt.tight_layout(); plt.savefig(IMG / "calibration.png", dpi=120); plt.close()

    # ---- Cost vs threshold, with sensitivity band on the cost ratio ----
    thresholds = np.linspace(0.01, 0.9, 60)
    plt.figure(figsize=(8, 5))
    for ratio, style in [(50, ":"), (100, "-"), (200, "--")]:
        c_missed = COST_VISIT * ratio
        costs = []
        for t in thresholds:
            alarm = test.risk_calibrated >= t
            fp = int((alarm & (test.label == 0)).sum())
            fn = int((~alarm & (test.label == 1)).sum())
            costs.append((fp * COST_VISIT + fn * c_missed) / 1000)
        costs = np.array(costs)
        best_t = thresholds[costs.argmin()]
        plt.plot(thresholds, costs, style, label=f"missed:visit = {ratio}:1 (best t={best_t:.2f})")
        if ratio == 100:
            metrics["best_threshold_ratio100"] = round(float(best_t), 3)
    plt.xlabel("alarm threshold on calibrated risk"); plt.ylabel("expected cost on test window ($k)")
    plt.title("Threshold is a business decision: expected cost vs alarm threshold")
    plt.legend(); plt.tight_layout(); plt.savefig(IMG / "cost_threshold.png", dpi=120); plt.close()

    # ---- Lead time for intercepted failures ----
    t_best = metrics["best_threshold_ratio100"]
    tp = test[(test.risk_calibrated >= t_best) & (test.label == 1)]
    plt.figure(figsize=(7, 4.5))
    plt.hist(tp.days_to_failure.dropna(), bins=np.arange(0.5, 8.5), edgecolor="white")
    plt.xlabel("days between alert and failure"); plt.ylabel("intercepted failures")
    plt.title("Lead time: an alert is only useful if it arrives days ahead")
    plt.tight_layout(); plt.savefig(IMG / "lead_time.png", dpi=120); plt.close()
    metrics["median_lead_days"] = float(tp.days_to_failure.median()) if len(tp) else None
    metrics["intercepted_at_best_t"] = int(len(tp))
    metrics["test_positives"] = int(test.label.sum())

    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print(f"figures -> {IMG}")


if __name__ == "__main__":
    main()
