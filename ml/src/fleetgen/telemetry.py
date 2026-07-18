"""Daily sensor telemetry: baselines + noise + calibration offsets + injected drift.

Realism knobs (all cheap, all disclosed):
- Per-machine calibration offsets: two healthy machines do not report identical
  baselines.
- Usage coupling: thermally-loaded sensors run slightly hotter on busy days.
- Weekend effect: scan volume drops, so usage-coupled signals dip.
- Missing days: random connectivity gaps, plus chronically flaky reporters,
  plus nothing at all while the machine is down.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .degradation import MachineHistory

# Sensors whose values rise a little with usage intensity (thermal load).
USAGE_COUPLED = {"compressor_temp", "gradient_temp", "tube_temp", "cooling_margin"}


def build_telemetry(
    machine: dict,
    hist: MachineHistory,
    dates: pd.DatetimeIndex,
    modality_cfg: dict,
    dq_cfg: dict,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Return long-format telemetry rows: (machine_id, date, sensor, value)."""
    n = len(dates)
    weekend = dates.dayofweek >= 5

    # Daily scan counts (usage): Poisson around baseline, weekend dip, zero when down.
    lam = machine["scans_per_day"] * np.where(weekend, 0.55, 1.0)
    scans = rng.poisson(lam).astype(float)
    scans[hist.down_mask] = 0.0
    usage_ratio = np.divide(scans, machine["scans_per_day"], out=np.ones(n), where=machine["scans_per_day"] > 0)

    # Missing-day mask: connectivity gaps + flaky reporters + downtime.
    miss_rate = dq_cfg["flaky_missing_day_rate"] if machine["flaky_reporter"] else dq_cfg["missing_day_rate"]
    missing = rng.random(n) < miss_rate
    missing |= hist.down_mask

    frames = []
    for sensor, s_cfg in modality_cfg["sensors"].items():
        sigma = s_cfg["sigma"]
        calib = rng.normal(0.0, dq_cfg["calibration_offset_sigma"] * sigma)
        values = (
            s_cfg["baseline"]
            + calib
            + rng.normal(0.0, sigma, n)
            + s_cfg["drift_sign"] * hist.drift_sigma.get(sensor, 0.0) * sigma
        )
        if sensor in USAGE_COUPLED:
            values = values + 0.3 * sigma * (usage_ratio - 1.0)
        frames.append(
            pd.DataFrame(
                {
                    "machine_id": machine["machine_id"],
                    "date": dates,
                    "sensor": sensor,
                    "value": values,
                }
            )[~missing]
        )

    # Scan counts are telemetry too (usage features come from here).
    frames.append(
        pd.DataFrame(
            {
                "machine_id": machine["machine_id"],
                "date": dates,
                "sensor": "scans_count",
                "value": scans,
            }
        )[~missing]
    )
    return pd.concat(frames, ignore_index=True)
