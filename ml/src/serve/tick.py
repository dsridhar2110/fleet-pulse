"""P7 — advance the world clock by one day (the daily cron + the demo button).

Loads each machine's persisted latent state, simulates one new day, appends the
day's telemetry / errors / failures / maintenance / tickets to Neon, rescores the
new day with the saved model bundle, rebuilds the decision + economics layer, and
moves the world clock forward. Idempotent-per-day: each call advances exactly one
simulated day from wherever the clock currently sits.

Usage:  python -m serve.tick            # advance one day
        python -m serve.tick --days 7   # advance a week
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

from sim.common import load_configs
from sim.physics import MachineSimState, step_machine_day
from db.engine import get_engine
from db.io import insert_rows, set_world_meta, upsert_machine_states
from serve.backfill import (TELEMETRY_COLS, ERROR_COLS, FAILURE_COLS, MAINT_COLS,
                            TICKET_COLS, _engineer_pools)
from pipeline.features_live import compute_panel, features_asof, load_frames
from models.train_live import compose_probs, load_bundle, ALL_HORIZONS
from models.decisions import build_decisions


def _seed(machine_id: str, day: int) -> int:
    h = int(hashlib.md5(f"{machine_id}:{day}".encode()).hexdigest()[:8], 16)
    return h % (2**31)


def advance_one_day(engine, model_version: str = "v-current", rebuild_decisions: bool = True) -> dict:
    t0 = time.time()
    fleet_cfg, fm_cfg = load_configs()
    with engine.connect() as c:
        clock = c.execute(text("SELECT value FROM world_meta WHERE key='clock'")).scalar_one()
        rows = c.execute(text("SELECT machine_id, state FROM machine_state")).fetchall()
        pools_countries = list(fleet_cfg["fleet"]["countries"].keys())
        country_by_machine = dict(c.execute(text("SELECT machine_id, country FROM machines")).fetchall())

    start = pd.Timestamp(clock["start_date"])
    new_day = int(clock["current_day"]) + 1
    new_date = start + pd.Timedelta(days=new_day)
    d = new_date.date()
    pools = _engineer_pools(pools_countries, np.random.default_rng(fleet_cfg["seed"]))

    buffers = {k: [] for k in ("telemetry", "errors", "failures", "maintenance", "tickets")}
    new_states = []
    n_fail = 0
    for machine_id, state_json in rows:
        st = MachineSimState.from_dict(state_json)
        rng = np.random.default_rng(_seed(machine_id, new_day))
        em = step_machine_day(st, new_day, new_date, fm_cfg, fleet_cfg, rng)
        tel = em["telemetry"]
        if tel:
            readings = {t["sensor"]: round(t["value"], 4) for t in tel if t["sensor"] != "scans_count"}
            scans = next((t["value"] for t in tel if t["sensor"] == "scans_count"), None)
            buffers["telemetry"].append((machine_id, d, st.modality, scans, json.dumps(readings)))
        for e in em["errors"]:
            buffers["errors"].append((machine_id, d, e["error_code"], e["family"], e["severity"]))
        for f in em["failures"]:
            buffers["failures"].append((machine_id, d, f["component"], f["sudden"], f["downtime_days"])); n_fail += 1
        for m in em["maintenance"]:
            buffers["maintenance"].append((machine_id, d, m["maintenance_type"], m["component"]))
        for tk in em["tickets"]:
            eng_id = str(rng.choice(pools[country_by_machine.get(machine_id, pools_countries[0])]))
            close = (new_date + pd.Timedelta(days=tk["downtime_days"])).date() if tk.get("repair_day") is not None \
                else (pd.Timestamp(tk["close_date"]).date() if tk.get("close_date") is not None else None)
            buffers["tickets"].append((machine_id, d, close, tk["ticket_type"], tk["component"],
                                       tk["part_replaced"], eng_id, tk["downtime_days"], tk["note_text"]))
        new_states.append((machine_id, d, st.to_dict()))

    # append the day
    insert_rows(engine, "telemetry_daily", TELEMETRY_COLS, buffers["telemetry"], jsonb_cols=("readings",))
    insert_rows(engine, "error_events", ERROR_COLS, buffers["errors"])
    insert_rows(engine, "failures", FAILURE_COLS, buffers["failures"])
    insert_rows(engine, "maintenance", MAINT_COLS, buffers["maintenance"])
    insert_rows(engine, "tickets", TICKET_COLS, buffers["tickets"])
    upsert_machine_states(engine, new_states)

    # rescore the new day (fast trailing-window features)
    bundle = load_bundle()
    since = (new_date - pd.Timedelta(days=130)).date()
    frames = load_frames(engine, up_to=str(d), since=str(since))
    panel = compute_panel(frames)
    f = features_asof(panel, new_date)
    X = f[bundle["feat_cols"]].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    P = compose_probs(bundle, X)
    with engine.begin() as c:
        c.execute(text("DELETE FROM predictions WHERE as_of_date = :d"), {"d": d})
    pred_rows = []
    for i, mid in enumerate(f["machine_id"].values):
        for j, h in enumerate(ALL_HORIZONS):
            pred_rows.append((mid, d, int(h), float(P[i, j]), model_version))
    insert_rows(engine, "predictions",
                ["machine_id", "as_of_date", "horizon_days", "p_fail", "model_version"], pred_rows)

    set_world_meta(engine, "clock", {
        "start_date": clock["start_date"], "current_date": str(d),
        "current_day": new_day, "window_months": clock.get("window_months", 36)})

    dec = build_decisions(engine) if rebuild_decisions else {}
    return {"date": str(d), "new_failures": n_fail, "telemetry_rows": len(buffers["telemetry"]),
            "scored_machines": len(f), "seconds": round(time.time() - t0, 1),
            "detection_rate": dec.get("detection_rate")}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=1)
    args = p.parse_args()
    engine = get_engine()
    for i in range(args.days):
        # only rebuild the decision layer on the final day of a multi-day run
        r = advance_one_day(engine, rebuild_decisions=(i == args.days - 1))
        print(json.dumps(r))


if __name__ == "__main__":
    main()
