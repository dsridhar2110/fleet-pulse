"""Error-code events and maintenance records.

Most error-code volume is deliberately BENIGN (system info, network blips,
operator messages) and uncorrelated with failure — so "error burst" features
have to be learned, not handed to the model. Warning families ramp with
component degradation; critical codes fire on the failure day itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .degradation import MachineHistory

# Three concrete codes per family, e.g. CRYO-201, CRYO-202, CRYO-203.
_CODES_PER_FAMILY = 3


def _family_codes(family: str, base: int) -> list[str]:
    return [f"{family}-{base + j}" for j in range(_CODES_PER_FAMILY)]


def build_error_events(
    machine: dict,
    hist: MachineHistory,
    dates: pd.DatetimeIndex,
    error_cfg: dict,
    rng: np.random.Generator,
) -> pd.DataFrame:
    n = len(dates)
    up = ~hist.down_mask  # no events while the machine is powered down
    rows = []

    # Benign families: constant daily Poisson rate.
    for fam, f_cfg in error_cfg["benign_families"].items():
        counts = rng.poisson(f_cfg["rate_per_day"], n) * up
        codes = _family_codes(fam, 100)
        for day_idx in np.nonzero(counts)[0]:
            for _ in range(counts[day_idx]):
                rows.append((dates[day_idx], rng.choice(codes), fam, "info"))

    # Warning families: rate ramps with degradation intensity.
    for fam, rate in hist.warn_rate.items():
        counts = rng.poisson(rate) * up
        codes = _family_codes(fam, 400)
        for day_idx in np.nonzero(counts)[0]:
            for _ in range(counts[day_idx]):
                rows.append((dates[day_idx], rng.choice(codes), fam, "warning"))

    # Critical codes on the failure day itself. NOTE: these are part of the
    # failure, not a precursor — the labelling step must never let a feature
    # window touch the failure day (leakage trap #1).
    for day_idx, comp, _sudden, _dt in hist.failures:
        fam = machine["warn_family_by_component"][comp]
        for _ in range(error_cfg["critical_on_failure"]):
            rows.append((dates[day_idx], f"{fam}-900", fam, "critical"))

    df = pd.DataFrame(rows, columns=["date", "error_code", "family", "severity"])
    df.insert(0, "machine_id", machine["machine_id"])
    return df


def build_maintenance(
    machine: dict, hist: MachineHistory, dates: pd.DatetimeIndex
) -> pd.DataFrame:
    rows = [
        {
            "machine_id": machine["machine_id"],
            "date": dates[day_idx],
            "maintenance_type": mtype,
            "component": comp,
        }
        for day_idx, mtype, comp in hist.maintenance
        if day_idx < len(dates)
    ]
    return pd.DataFrame(rows)


def build_failures(
    machine: dict, hist: MachineHistory, dates: pd.DatetimeIndex
) -> pd.DataFrame:
    rows = [
        {
            "machine_id": machine["machine_id"],
            "failure_date": dates[day_idx],
            "component": comp,
            "sudden": sudden,
            "downtime_days": downtime,
        }
        for day_idx, comp, sudden, downtime in hist.failures
    ]
    return pd.DataFrame(rows)
