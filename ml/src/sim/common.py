"""Config loading + derived constants shared across the incremental simulator."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def load_configs(
    fleet_config: str | None = None, failure_modes: str | None = None
) -> tuple[dict, dict]:
    """Return (fleet_cfg, failure_modes_cfg). Cached by path."""
    fc = Path(fleet_config) if fleet_config else ROOT / "config/fleet_config.yaml"
    fm = Path(failure_modes) if failure_modes else ROOT / "config/failure_modes.yaml"
    return yaml.safe_load(fc.read_text()), yaml.safe_load(fm.read_text())


def mean_scans_by_modality(fm_cfg: dict) -> dict[str, float]:
    """Fleet-average scans/day per modality — the usage-factor denominator."""
    return {
        m: float(np.mean(fm_cfg["modalities"][m]["usage"]["scans_per_day"]))
        for m in fm_cfg["modalities"]
    }


# Sensors whose values rise a little with usage intensity (thermal load).
# Kept identical to fleetgen.telemetry so incremental output matches batch.
USAGE_COUPLED = {"compressor_temp", "gradient_temp", "tube_temp", "cooling_margin"}
