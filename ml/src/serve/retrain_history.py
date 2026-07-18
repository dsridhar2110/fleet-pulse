"""Replace the illustrative evolution trajectory with REAL retrains.

Retrains the model at five quarterly cutoffs across the deployment year (each a
genuine fit on data available up to that date, scored on its own held-out split)
and feeds the measured metrics into `build_evolution`. This turns the Model &
Governance page from an illustrative replay into an honest continual-learning
record: the metrics you see are the metrics those retrains actually produced.

Usage:  python -u -m serve.retrain_history
"""

from __future__ import annotations

import json

import pandas as pd
from sqlalchemy import text

from db.engine import get_engine
from models.train_live import train_and_score
from models.evolution import build_evolution


def run(months: int = 12) -> dict:
    engine = get_engine()
    with engine.connect() as c:
        current = pd.Timestamp(c.execute(
            text("SELECT value FROM world_meta WHERE key='clock'")).scalar_one()["current_date"])
    stamps = list(pd.date_range(current - pd.Timedelta(days=int(months * 30.44)), current, periods=5))

    real = []
    for i, ts in enumerate(stamps):
        m = train_and_score(engine, up_to=str(ts.date()), write=False, save_model=False)["metrics"]
        rec = {"pr_auc": round(m.get("pr_auc_7d") or 0.0, 3),
               "precision_at_20": round(m.get("precision_at_20") or 0.0, 3),
               "recall_at_20": round(m.get("recall_at_20") or 0.0, 3),
               "lead_time_days": 3}
        real.append(rec)
        print(f"v1.{i}  cutoff {ts.date()}  →  {rec}", flush=True)

    out = build_evolution(engine, months=months, real_metrics=real)
    out["real_trajectory"] = real
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
