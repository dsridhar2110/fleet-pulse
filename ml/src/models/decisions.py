"""P5 — decision policy, outcome resolution, and economics.

From the weekly predictions the service team acts: a top-k worklist is dispatched
for inspection (operational, 7-day risk); longer-horizon risk drives planning
decisions. Past decisions are then *resolved* against what actually happened
(caught / false alarm / missed), and the money is tallied into `impact_daily` —
the backward scoreboard and the forward worklist the dashboard is built around.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.io import insert_rows
from models.econ import ASSUMPTIONS, savings_if_caught

DISPATCH_COLS = ["machine_id", "as_of_date", "horizon_days", "action", "risk_score",
                 "expected_cost", "expected_savings", "status", "outcome", "outcome_date",
                 "model_version", "rationale"]
IMPACT_COLS = ["as_of_date", "fleet_expected_loss", "worklist_size", "worklist_net_savings",
               "downtime_days_avoided", "do_nothing_cost", "cumulative_net_savings",
               "assumptions"]


def _load(engine: Engine):
    with engine.connect() as c:
        preds = pd.read_sql(text("SELECT machine_id, as_of_date, horizon_days, p_fail, "
                                 "model_version FROM predictions"), c)
        fails = pd.read_sql(text("SELECT machine_id, failure_date, downtime_days FROM failures"), c)
        clock = pd.read_sql(text("SELECT value FROM world_meta WHERE key='clock'"), c)
    preds["as_of_date"] = pd.to_datetime(preds["as_of_date"])
    fails["failure_date"] = pd.to_datetime(fails["failure_date"])
    current = pd.Timestamp(clock["value"].iloc[0]["current_date"])
    return preds, fails, current


def _next_failure_within(fails_by_machine, mid, as_of, horizon):
    arr = fails_by_machine.get(mid)
    if arr is None:
        return None
    hi = as_of + pd.Timedelta(days=horizon)
    m = arr[(arr["failure_date"] > as_of) & (arr["failure_date"] <= hi)]
    return None if m.empty else m.iloc[0]


def build_decisions(engine: Engine, months: int = 12, model_version: str = "v-current") -> dict:
    preds, fails, current = _load(engine)
    k = ASSUMPTIONS["worklist_k"]
    avg_dt = float(fails["downtime_days"].mean())
    fbm = {m: g.sort_values("failure_date") for m, g in fails.groupby("machine_id")}

    p7 = preds[preds.horizon_days == 7]
    window_start = current - pd.Timedelta(days=int(months * 30.44))
    all_dates = sorted(d for d in p7["as_of_date"].unique() if d >= window_start)
    # A service team runs ONE weekly worklist — thin to ~7-day spacing so the
    # daily prediction tail doesn't double-count decisions in the last month.
    as_ofs, last = [], None
    for d in all_dates:
        if last is None or (d - last).days >= 6:
            as_ofs.append(d); last = d

    dec_rows, impact_rows = [], []
    cum = 0.0
    for as_of in as_ofs:
        day = p7[p7.as_of_date == as_of][["machine_id", "p_fail"]].copy()
        if day.empty:
            continue
        day = day.sort_values("p_fail", ascending=False)
        worklist = day.head(k)
        resolved = as_of < current  # outcomes are only known for the past

        # who actually failed within 7d (for missed detection + recall)
        actual = {m for m in day.machine_id
                  if _next_failure_within(fbm, m, as_of, 7) is not None}
        dispatched = set(worklist.machine_id)

        # fleet expected loss (do-nothing risk this week)
        fleet_loss = float((day["p_fail"] * avg_dt * ASSUMPTIONS["downtime_cost_per_day"]).sum())

        week_savings, week_avoided = 0.0, 0.0
        for r in worklist.itertuples():
            nf = _next_failure_within(fbm, r.machine_id, as_of, 7)
            exp_save = r.p_fail * savings_if_caught(avg_dt)
            if resolved:
                if nf is not None:
                    outcome, odate = "caught", (as_of + pd.Timedelta(days=1)).date()
                    week_savings += savings_if_caught(nf["downtime_days"])
                    week_avoided += float(nf["downtime_days"]) - ASSUMPTIONS["planned_downtime_days"]
                else:
                    outcome, odate = "false_alarm", (as_of + pd.Timedelta(days=7)).date()
                    week_savings -= ASSUMPTIONS["proactive_visit_cost"]
                status = "resolved"
            else:
                outcome, odate, status = "pending", None, "dispatched"
                week_savings += exp_save
            dec_rows.append((r.machine_id, as_of.date(), 7, "dispatch", float(r.p_fail),
                             float(ASSUMPTIONS["proactive_visit_cost"]), float(exp_save),
                             status, outcome, odate, model_version,
                             f"top-{k} weekly worklist (p7={r.p_fail:.2f})"))

        # missed = failed in-horizon but not dispatched (past weeks only)
        if resolved:
            for m in actual - dispatched:
                nf = _next_failure_within(fbm, m, as_of, 7)
                dec_rows.append((m, as_of.date(), 7, "defer",
                                 float(day[day.machine_id == m]["p_fail"].iloc[0]),
                                 0.0, 0.0, "resolved", "missed",
                                 (as_of + pd.Timedelta(days=1)).date(), model_version,
                                 "below worklist cut — failure not caught"))

        cum += week_savings
        impact_rows.append((as_of.date(), fleet_loss, len(worklist), float(week_savings),
                            float(week_avoided),
                            float(fleet_loss), float(cum),
                            _json(ASSUMPTIONS)))

    # write
    with engine.begin() as c:
        c.execute(text("DELETE FROM decisions"))
        c.execute(text("DELETE FROM impact_daily"))
    n_dec = insert_rows(engine, "decisions", DISPATCH_COLS, dec_rows, page_size=2000)
    n_imp = insert_rows(engine, "impact_daily", IMPACT_COLS, impact_rows,
                        jsonb_cols=("assumptions",), page_size=500)

    resolved_dec = [d for d in dec_rows if d[7] == "resolved"]
    caught = sum(1 for d in resolved_dec if d[8] == "caught")
    missed = sum(1 for d in resolved_dec if d[8] == "missed")
    false_alarm = sum(1 for d in resolved_dec if d[8] == "false_alarm")
    return {"decisions": n_dec, "impact_points": n_imp, "cumulative_net_savings": round(cum),
            "caught": caught, "missed": missed, "false_alarm": false_alarm,
            "detection_rate": round(caught / max(1, caught + missed), 3)}


def _json(d):
    import json
    return json.dumps(d)


if __name__ == "__main__":
    from db.engine import get_engine
    import json
    print(json.dumps(build_decisions(get_engine()), indent=2))
