"""P3 — backfill the last N months of history into Neon.

Builds the customer base + a growing fleet (onboarding schedule), commissions
each machine on its commission day, then steps the whole fleet day-by-day,
streaming telemetry / errors / failures / maintenance / tickets into Postgres in
monthly flushes. Finishes by persisting each machine's latent state (so the daily
cron can resume) and the world clock.

Usage:
    python -m serve.backfill --months 36 --end-date 2026-07-18 --reset
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict

import numpy as np
import pandas as pd

from sim.common import load_configs, mean_scans_by_modality
from sim.physics import init_machine_state, step_machine_day
from sim.world import build_world
from db.engine import get_engine, init_schema
from db.io import insert_rows, set_world_meta, truncate_all, upsert_machine_states

TELEMETRY_COLS = ["machine_id", "date", "modality", "scans_count", "readings"]
ERROR_COLS = ["machine_id", "date", "error_code", "family", "severity"]
FAILURE_COLS = ["machine_id", "failure_date", "component", "sudden", "downtime_days"]
MAINT_COLS = ["machine_id", "date", "maintenance_type", "component"]
TICKET_COLS = ["machine_id", "open_date", "close_date", "ticket_type", "component",
               "part_replaced", "engineer_id", "downtime_days", "note_text"]


def _engineer_pools(countries, rng):
    return {c: [f"ENG-{c}-{i + 1:02d}" for i in range(int(rng.integers(3, 7)))]
            for c in countries}


def _flush(engine, buffers):
    n = 0
    n += insert_rows(engine, "telemetry_daily", TELEMETRY_COLS, buffers["telemetry"],
                     jsonb_cols=("readings",))
    n += insert_rows(engine, "error_events", ERROR_COLS, buffers["errors"])
    n += insert_rows(engine, "failures", FAILURE_COLS, buffers["failures"])
    n += insert_rows(engine, "maintenance", MAINT_COLS, buffers["maintenance"])
    n += insert_rows(engine, "tickets", TICKET_COLS, buffers["tickets"])
    for k in buffers:
        buffers[k].clear()
    return n


def run_backfill(months=36, end_date=None, reset=True, flush_every=30) -> dict:
    fleet_cfg, fm_cfg = load_configs()
    seed = fleet_cfg["seed"]
    end = pd.Timestamp(end_date) if end_date else pd.Timestamp.today().normalize()
    window_days = int(months * 30.44)
    start = end - pd.Timedelta(days=window_days - 1)
    dates = pd.date_range(start, periods=window_days, freq="D")
    mean_scans = mean_scans_by_modality(fm_cfg)

    rng = np.random.default_rng(seed)
    customers, machines = build_world(fleet_cfg, fm_cfg, months, rng, window_start=start)
    pools = _engineer_pools(list(fleet_cfg["fleet"]["countries"].keys()), rng)
    country_by_machine = dict(zip(machines["machine_id"], machines["country"]))

    engine = get_engine()
    init_schema(engine)
    if reset:
        truncate_all(engine)

    insert_rows(engine, "customers",
                ["customer_id", "name", "country", "region", "segment", "onboarded_date"],
                list(customers[["customer_id", "name", "country", "region",
                                "segment", "onboarded_date"]].itertuples(index=False, name=None)))
    insert_rows(engine, "machines",
                ["machine_id", "customer_id", "modality", "model", "country", "region",
                 "hospital_name", "install_date", "commission_date", "scans_per_day",
                 "flaky_reporter", "status"],
                list(machines[["machine_id", "customer_id", "modality", "model", "country",
                               "region", "hospital_name", "install_date", "commission_date",
                               "scans_per_day", "flaky_reporter", "status"]]
                     .itertuples(index=False, name=None)))

    by_commission: dict[int, list] = defaultdict(list)
    for idx, rec in enumerate(machines.to_dict("records")):
        by_commission[rec["commission_day"]].append((idx, rec))

    states: dict[str, list] = {}   # machine_id -> [state, rng]
    buffers = {k: [] for k in ("telemetry", "errors", "failures", "maintenance", "tickets")}
    t0 = time.time()
    totals = {k: 0 for k in buffers}

    for day, date in enumerate(dates):
        d = date.date()
        for idx, rec in by_commission.get(day, []):
            r = np.random.default_rng(seed * 100_000 + idx)
            age = max(0.0, (date - pd.Timestamp(rec["install_date"])).days / 365.25)
            st = init_machine_state(rec, day, age, fm_cfg, fleet_cfg,
                                    mean_scans[rec["modality"]], r)
            states[rec["machine_id"]] = [st, r]

        for mid, (st, r) in states.items():
            em = step_machine_day(st, day, date, fm_cfg, fleet_cfg, r)
            tel = em["telemetry"]
            if tel:
                readings = {t["sensor"]: round(t["value"], 4)
                            for t in tel if t["sensor"] != "scans_count"}
                scans = next((t["value"] for t in tel if t["sensor"] == "scans_count"), None)
                buffers["telemetry"].append((mid, d, st.modality, scans, json.dumps(readings)))
            for e in em["errors"]:
                buffers["errors"].append((mid, d, e["error_code"], e["family"], e["severity"]))
            for f in em["failures"]:
                buffers["failures"].append((mid, d, f["component"], f["sudden"], f["downtime_days"]))
            for m in em["maintenance"]:
                buffers["maintenance"].append((mid, d, m["maintenance_type"], m["component"]))
            for tk in em["tickets"]:
                eng_id = str(r.choice(pools[country_by_machine[mid]]))
                if tk.get("repair_day") is not None:
                    close = dates[min(tk["repair_day"], window_days - 1)].date()
                elif tk.get("close_date") is not None:
                    close = pd.Timestamp(tk["close_date"]).date()
                else:
                    close = None
                buffers["tickets"].append((
                    mid, pd.Timestamp(tk["open_date"]).date(), close, tk["ticket_type"],
                    tk["component"], tk["part_replaced"], eng_id, tk["downtime_days"],
                    tk["note_text"]))

        if day % flush_every == flush_every - 1:
            for k in totals:
                totals[k] += len(buffers[k])
            _flush(engine, buffers)
            print(f"  day {day + 1}/{window_days} ({d}) — active {len(states)} machines, "
                  f"{totals['telemetry']:,} telemetry rows so far [{time.time() - t0:.0f}s]")

    for k in totals:
        totals[k] += len(buffers[k])
    _flush(engine, buffers)

    upsert_machine_states(engine, [(mid, dates[-1].date(), st.to_dict())
                                   for mid, (st, r) in states.items()])
    set_world_meta(engine, "clock", {
        "start_date": str(start.date()), "current_date": str(dates[-1].date()),
        "current_day": window_days - 1, "window_months": months})
    set_world_meta(engine, "fleet", {"n_customers": len(customers), "n_machines": len(machines)})

    totals["customers"], totals["machines"] = len(customers), len(machines)
    totals["seconds"] = round(time.time() - t0, 1)
    return totals


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=36)
    p.add_argument("--end-date", default=None, help="world 'today' (YYYY-MM-DD); default = today")
    p.add_argument("--reset", action="store_true", help="truncate all tables first")
    p.add_argument("--flush-every", type=int, default=30)
    args = p.parse_args()

    t = run_backfill(args.months, args.end_date, args.reset, args.flush_every)
    print("\n=== backfill complete ===")
    for k, v in t.items():
        print(f"  {k:12s}: {v:,}" if isinstance(v, int) else f"  {k:12s}: {v}")


if __name__ == "__main__":
    main()
