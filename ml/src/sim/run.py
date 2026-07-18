"""In-memory driver for the incremental simulator.

`simulate_range` commissions a fleet and steps every machine day-by-day over a
window, collecting the same row schema the batch generator produced. It is the
substrate for both the P2 equivalence test and the P3 Postgres backfill (which
wraps it with per-day writes + state persistence).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fleetgen.fleet_master import build_fleet
from .common import load_configs, mean_scans_by_modality
from .physics import MachineSimState, init_machine_state, step_machine_day


# --------------------------------------------------------------------------- #
# RNG (de)serialisation — lets a machine's stream resume across DB round-trips
# --------------------------------------------------------------------------- #
def rng_to_state(rng: np.random.Generator) -> dict:
    return rng.bit_generator.state


def rng_from_state(state: dict) -> np.random.Generator:
    bg = np.random.PCG64()
    bg.state = state
    return np.random.Generator(bg)


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def commission_fleet(
    fleet_df: pd.DataFrame, start_date: pd.Timestamp, fm_cfg: dict, fleet_cfg: dict, seed: int,
) -> dict[str, tuple[MachineSimState, np.random.Generator]]:
    """Build latent state + a per-machine RNG for every machine, at world-day 0."""
    mean_scans = mean_scans_by_modality(fm_cfg)
    states: dict[str, tuple[MachineSimState, np.random.Generator]] = {}
    for idx, machine in enumerate(fleet_df.to_dict("records")):
        rng = np.random.default_rng(seed * 100_000 + idx)
        age = (start_date - machine["install_date"]).days / 365.25
        state = init_machine_state(
            machine, commission_day=0, age_years_at_commission=max(0.0, age),
            fm_cfg=fm_cfg, fleet_cfg=fleet_cfg,
            mean_scans=mean_scans[machine["modality"]], rng=rng,
        )
        states[machine["machine_id"]] = (state, rng)
    return states


def simulate_range(
    n_days: int = 365,
    fleet_config: str | None = None,
    failure_modes: str | None = None,
    start_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the whole fleet day-by-day for `n_days`. Returns batch-shaped frames."""
    fleet_cfg, fm_cfg = load_configs(fleet_config, failure_modes)
    seed = fleet_cfg["seed"]
    start = pd.Timestamp(start_date or fleet_cfg["simulation"]["start_date"])
    dates = pd.date_range(start, periods=n_days, freq="D")

    fleet = build_fleet(fleet_cfg, fm_cfg, np.random.default_rng(seed))
    states = commission_fleet(fleet, start, fm_cfg, fleet_cfg, seed)

    buckets: dict[str, list[dict]] = {
        k: [] for k in ("telemetry", "errors", "failures", "maintenance", "tickets")}

    for day, date in enumerate(dates):
        for _mid, (state, rng) in states.items():
            emitted = step_machine_day(state, day, date, fm_cfg, fleet_cfg, rng)
            for key, rows in emitted.items():
                if rows:
                    buckets[key].extend(rows)

    frames = {k: pd.DataFrame(v) for k, v in buckets.items()}
    frames["fleet"] = fleet
    return frames
