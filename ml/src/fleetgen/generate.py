"""Generate the full synthetic fleet dataset.

Usage:
    python -m fleetgen.generate --config config/fleet_config.yaml

Writes partitioned parquet under data/raw/ and prints the summary stats that
gate the design (machine-week failure rate must land in the 1-3% band).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .degradation import simulate_machine
from .events import build_error_events, build_failures, build_maintenance
from .fleet_master import build_fleet
from .telemetry import build_telemetry
from .tickets import build_tickets

ROOT = Path(__file__).resolve().parents[2]


def _engineer_pools(countries: list[str], rng: np.random.Generator) -> dict[str, list[str]]:
    """3-6 field engineers per country."""
    return {
        c: [f"ENG-{c}-{i + 1:02d}" for i in range(int(rng.integers(3, 7)))] for c in countries
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config/fleet_config.yaml"))
    parser.add_argument("--out", default=str(ROOT / "data/raw"))
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    fm_cfg = yaml.safe_load((ROOT / "config/failure_modes.yaml").read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(cfg["seed"])
    t0 = time.time()

    dates = pd.date_range(cfg["simulation"]["start_date"], cfg["simulation"]["end_date"], freq="D")
    sim_days = len(dates)
    sim_start = dates[0]

    fleet = build_fleet(cfg, fm_cfg, rng)
    fleet["age_years_at_start"] = (sim_start - fleet["install_date"]).dt.days / 365.25
    pools = _engineer_pools(list(cfg["fleet"]["countries"].keys()), rng)

    mean_scans_by_mod = {
        m: float(np.mean(fm_cfg["modalities"][m]["usage"]["scans_per_day"]))
        for m in fm_cfg["modalities"]
    }

    telemetry, errors, failures, maintenance, tickets = [], [], [], [], []

    for idx, machine in enumerate(fleet.to_dict("records")):
        m_rng = np.random.default_rng(cfg["seed"] * 100_000 + idx)  # per-machine reproducibility
        modality_cfg = fm_cfg["modalities"][machine["modality"]]
        machine["warn_family_by_component"] = {
            comp: c_cfg["precursor"]["warn_code_family"]
            for comp, c_cfg in modality_cfg["components"].items()
        }
        machine["engineer_pool"] = pools[machine["country"]]

        hist = simulate_machine(
            machine,
            sim_days,
            cfg["simulation"],
            cfg["maintenance"],
            modality_cfg,
            mean_scans_by_mod[machine["modality"]],
            m_rng,
        )
        tel = build_telemetry(machine, hist, dates, modality_cfg, cfg["data_quality"], m_rng)
        tel["modality"] = machine["modality"]
        telemetry.append(tel)
        errors.append(build_error_events(machine, hist, dates, fm_cfg["error_codes"], m_rng))
        failures.append(build_failures(machine, hist, dates))
        maintenance.append(build_maintenance(machine, hist, dates))
        tickets.append(build_tickets(machine, hist, dates, modality_cfg, m_rng))

    fleet = fleet.drop(columns=["age_years_at_start"])
    fleet.to_parquet(out / "fleet_master.parquet", index=False)

    tel_df = pd.concat(telemetry, ignore_index=True)
    tel_df.to_parquet(out / "telemetry", partition_cols=["modality"], index=False)

    err_df = pd.concat(errors, ignore_index=True)
    err_df.to_parquet(out / "error_events.parquet", index=False)

    fail_df = pd.concat([f for f in failures if not f.empty], ignore_index=True)
    fail_df.to_parquet(out / "failures.parquet", index=False)

    pd.concat(maintenance, ignore_index=True).to_parquet(out / "maintenance.parquet", index=False)
    pd.concat(tickets, ignore_index=True).to_parquet(out / "tickets.parquet", index=False)

    # ---- Gate stats ----
    n_machines = len(fleet)
    n_weeks = sim_days / 7.0
    machine_weeks = n_machines * n_weeks
    # A machine-week is "positive" if a failure occurs in it; approximate by
    # counting failure events (multiple failures same machine-week are rare).
    rate = len(fail_df) / machine_weeks
    sudden_share = fail_df["sudden"].mean()

    print(f"machines: {n_machines} | days: {sim_days} | telemetry rows: {len(tel_df):,}")
    print(f"error events: {len(err_df):,} (warning share: {(err_df.severity == 'warning').mean():.1%})")
    print(f"failures: {len(fail_df)} | machine-week positive rate: {rate:.2%} (target 1-3%)")
    print(f"sudden (no precursor) share: {sudden_share:.1%} (target ~15%)")
    print(f"tickets: {sum(len(t) for t in tickets):,}")
    print(f"done in {time.time() - t0:.1f}s -> {out}")

    if not 0.01 <= rate <= 0.03:
        print("WARNING: machine-week failure rate outside 1-3% gate — tune event_rate_multiplier.")


if __name__ == "__main__":
    main()
