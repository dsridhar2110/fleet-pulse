"""P2 acceptance: the incremental (daily) simulator must reproduce the batch
generator's *statistical* signature — not row-for-row (the RNG draw order
differs by construction), but every design gate the batch generator is held to:

  * machine-week failure rate lands in the disclosed 1-3% band
  * ~15% of failures are sudden (no precursor)
  * telemetry sensor means sit on their configured baselines
  * non-sudden failures are genuinely preceded by sensor drift (signal exists)
  * benign error volume dominates (error-burst features are earned, not given)

These are the same gates `fleetgen.generate` prints; if the refactor drifted
from the physics, one of them breaks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sim.common import load_configs  # noqa: E402
from sim.run import simulate_range  # noqa: E402

N_DAYS = 365


def _frames():
    if not hasattr(_frames, "cache"):
        _frames.cache = simulate_range(n_days=N_DAYS)
    return _frames.cache


def test_failure_rate_in_band():
    f = _frames()
    n_machines = len(f["fleet"])
    machine_weeks = n_machines * (N_DAYS / 7.0)
    rate = len(f["failures"]) / machine_weeks
    assert 0.01 <= rate <= 0.03, f"machine-week failure rate {rate:.2%} outside 1-3% gate"


def test_sudden_share_near_config():
    f = _frames()
    fleet_cfg, _ = load_configs()
    target = fleet_cfg["simulation"]["sudden_failure_fraction"]
    share = f["failures"]["sudden"].mean()
    assert abs(share - target) < 0.08, f"sudden share {share:.1%} far from target {target:.0%}"


def test_telemetry_baselines():
    f = _frames()
    _, fm_cfg = load_configs()
    tel = f["telemetry"]
    # Pick a stable, non-usage-coupled sensor per modality and check its mean.
    checks = {"MRI": ("helium_level", 97.0), "CT": ("detector_noise", 1.0),
              "XRAY": ("voltage_ripple", 1.0)}
    for modality, (sensor, baseline) in checks.items():
        vals = tel[(tel.modality == modality) & (tel.sensor == sensor)]["value"]
        assert len(vals) > 1000, f"too few {modality}/{sensor} rows"
        # generous tolerance: calibration offsets + drift pull the mean around a little
        assert abs(vals.mean() - baseline) < 1.0, \
            f"{modality}/{sensor} mean {vals.mean():.2f} off baseline {baseline}"


def test_benign_error_volume_dominates():
    f = _frames()
    sev = f["errors"]["severity"]
    info_share = (sev == "info").mean()
    assert info_share > 0.5, f"benign/info share only {info_share:.1%} — burst features not earned"


def test_precursor_signal_exists():
    """A non-sudden failure should show elevated warning-code volume in the 30
    days before it, versus a matched quiet baseline window for the same machine."""
    f = _frames()
    fails = f["failures"]
    non_sudden = fails[~fails["sudden"]]
    assert len(non_sudden) > 20, "not enough non-sudden failures to test precursor"

    warn = f["errors"][f["errors"].severity == "warning"].copy()
    warn["date"] = pd.to_datetime(warn["date"])
    by_machine = {m: g["date"].values for m, g in warn.groupby("machine_id")}

    pre, base = [], []
    for r in non_sudden.itertuples():
        dates = by_machine.get(r.machine_id)
        if dates is None:
            continue
        fd = np.datetime64(pd.Timestamp(r.failure_date))
        pre.append(int(((dates >= fd - np.timedelta64(30, "D")) & (dates < fd)).sum()))
        base.append(int(((dates >= fd - np.timedelta64(120, "D")) &
                         (dates < fd - np.timedelta64(90, "D"))).sum()))
    assert np.mean(pre) > 1.5 * np.mean(base) + 1e-9, \
        f"pre-failure warn volume {np.mean(pre):.2f} not elevated over baseline {np.mean(base):.2f}"


def test_state_roundtrips_through_json():
    """Latent state must survive a JSON round-trip (it persists to Postgres daily)."""
    import json
    from sim.physics import MachineSimState

    f = simulate_range(n_days=10)  # short run just to build a state
    fleet_cfg, fm_cfg = load_configs()
    from sim.run import commission_fleet
    states = commission_fleet(f["fleet"].head(3), pd.Timestamp("2025-01-01"),
                              fm_cfg, fleet_cfg, fleet_cfg["seed"])
    state = next(iter(states.values()))[0]
    d = json.loads(json.dumps(state.to_dict()))
    back = MachineSimState.from_dict(d)
    assert back.machine_id == state.machine_id
    assert set(back.components) == set(state.components)
    assert back.components[next(iter(back.components))].age_years == \
        state.components[next(iter(state.components))].age_years
