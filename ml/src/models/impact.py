"""Business Impact Engine — turn calibrated risk scores into money.

Two views:
  1. current_week  — the decision view: expected loss per machine as of the latest
     scoring week, and what the top-K inspection worklist is expected to buy.
  2. backtest      — the proof view: replay the test window (Nov-Dec) week by week,
     count what a top-K worklist would have actually caught, and price it.

All economics are disclosed order-of-magnitude assumptions (see ASSUMPTIONS).
Writes ml/data/app/impact.json and web/public/data/impact.json.

Run:  PYTHONPATH=src .venv/bin/python src/models/impact.py
"""
import json
from pathlib import Path

import pandas as pd

ML = Path(__file__).resolve().parents[2]

ASSUMPTIONS = {
    "downtime_cost_per_day_usd": 27_000,   # lost scanning revenue + disruption, order of magnitude
    "inspection_visit_cost_usd": 800,      # proactive engineer visit
    "worklist_size": 20,                   # weekly inspection budget
    "note": (
        "Synthetic-data illustration. Assumes a proactive inspection converts the "
        "unplanned downtime of a caught failure into a planned visit (downtime cost "
        "avoided; repair parts/labour still incurred either way, so excluded from both sides)."
    ),
}

DAY_COST = ASSUMPTIONS["downtime_cost_per_day_usd"]
VISIT = ASSUMPTIONS["inspection_visit_cost_usd"]
K = ASSUMPTIONS["worklist_size"]


def load():
    scores = pd.read_parquet(ML / "data" / "app" / "scores.parquet")
    failures = pd.read_parquet(ML / "data" / "raw" / "failures.parquet")
    fleet = pd.read_parquet(ML / "data" / "raw" / "fleet_master.parquet")
    return scores, failures, fleet


def current_week_view(scores: pd.DataFrame, failures: pd.DataFrame, fleet: pd.DataFrame) -> dict:
    """Expected-money view of the latest scoring week (the live worklist)."""
    as_of = scores["date"].max()
    week = scores[scores["date"] == as_of].copy()
    med_downtime = float(failures["downtime_days"].median())

    week["expected_downtime_days"] = week["risk_calibrated"] * med_downtime
    week["expected_loss_usd"] = week["expected_downtime_days"] * DAY_COST
    week = week.sort_values("risk_calibrated", ascending=False)

    top = week.head(K)
    expected_avoided = float(top["expected_loss_usd"].sum())
    spend = K * VISIT

    top_out = (
        top.merge(fleet[["machine_id", "modality", "country", "hospital_name"]], on="machine_id")
        [["machine_id", "modality", "country", "hospital_name", "risk_calibrated", "expected_loss_usd"]]
        .assign(risk_calibrated=lambda d: d["risk_calibrated"].round(4),
                expected_loss_usd=lambda d: d["expected_loss_usd"].round(0))
        .to_dict(orient="records")
    )

    return {
        "as_of": str(as_of.date()),
        "fleet_expected_loss_usd": round(float(week["expected_loss_usd"].sum()), 0),
        "worklist_expected_cost_avoided_usd": round(expected_avoided, 0),
        "worklist_inspection_spend_usd": spend,
        "worklist_expected_net_savings_usd": round(expected_avoided - spend, 0),
        "top_worklist": top_out,
    }


def backtest_view(scores: pd.DataFrame, failures: pd.DataFrame) -> dict:
    """Replay the held-out test window: what would the weekly top-K worklist have bought?"""
    test = scores[scores["split"] == "test"].copy()
    weeks = sorted(test["date"].unique())

    caught_downtime = missed_downtime = 0.0
    caught = missed = 0
    for wk in weeks:
        snap = test[test["date"] == wk].sort_values("risk_calibrated", ascending=False)
        flagged = set(snap.head(K)["machine_id"])
        positives = snap[snap["label"] == 1]
        for _, row in positives.iterrows():
            # the failure this label points at: first failure within (wk, wk+7]
            f = failures[(failures["machine_id"] == row["machine_id"])
                         & (failures["failure_date"] > wk)
                         & (failures["failure_date"] <= wk + pd.Timedelta(days=7))]
            days = float(f["downtime_days"].sum()) if len(f) else float(failures["downtime_days"].median())
            if row["machine_id"] in flagged:
                caught += 1
                caught_downtime += days
            else:
                missed += 1
                missed_downtime += days

    spend = len(weeks) * K * VISIT
    avoided = caught_downtime * DAY_COST
    still_lost = missed_downtime * DAY_COST
    do_nothing = (caught_downtime + missed_downtime) * DAY_COST

    return {
        "window": f"{pd.Timestamp(weeks[0]).date()} → {pd.Timestamp(weeks[-1]).date()}",
        "weeks": len(weeks),
        "inspection_visits": len(weeks) * K,
        "inspection_spend_usd": spend,
        "failures_in_window": caught + missed,
        "failures_caught_by_worklist": caught,
        "failures_missed": missed,
        "downtime_days_avoided": round(caught_downtime, 1),
        "downtime_cost_avoided_usd": round(avoided, 0),
        "net_savings_usd": round(avoided - spend, 0),
        "cost_of_missed_failures_usd": round(still_lost, 0),
        "do_nothing_cost_usd": round(do_nothing, 0),
        "downtime_cost_reduction_pct": round(100 * avoided / do_nothing, 1) if do_nothing else 0.0,
    }


def main():
    scores, failures, fleet = load()
    impact = {
        "assumptions": ASSUMPTIONS,
        "current_week": current_week_view(scores, failures, fleet),
        "backtest": backtest_view(scores, failures),
    }
    for out in [ML / "data" / "app" / "impact.json",
                ML.parent / "web" / "public" / "data" / "impact.json"]:
        out.write_text(json.dumps(impact, indent=2))
        print("wrote", out)

    cw, bt = impact["current_week"], impact["backtest"]
    print(f"\n=== Business Impact Engine ===")
    print(f"As of {cw['as_of']}: fleet expected loss ${cw['fleet_expected_loss_usd']:,.0f}; "
          f"top-{K} worklist → expected net savings ${cw['worklist_expected_net_savings_usd']:,.0f}/week")
    print(f"Backtest {bt['window']}: {bt['failures_caught_by_worklist']}/{bt['failures_in_window']} failures caught, "
          f"{bt['downtime_days_avoided']} downtime days avoided, net savings ${bt['net_savings_usd']:,.0f} "
          f"({bt['downtime_cost_reduction_pct']}% of do-nothing downtime cost)")


if __name__ == "__main__":
    main()
