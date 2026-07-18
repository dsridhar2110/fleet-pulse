"""Component-level degradation engine.

Failures are draws from Weibull lifetime distributions on component EFFECTIVE
AGE, so machine age, usage intensity, and time-since-maintenance are genuinely
predictive — the model has real physics to learn, not decoration.

Key modelling choices (all disclosed in docs/synthetic_data_design.md):
- Weibull shape k > 1 => wear-out (hazard increases with age).
- Usage-driven components (CT/X-ray tubes) accrue effective age with scan
  volume, not calendar time.
- Corrective repair is IMPERFECT: effective age resets to a fraction, not 0.
- Preventive maintenance shaves a fraction off effective age.
- A configured fraction of failures are SUDDEN (no precursor at all), and
  machines also exhibit FALSE precursor episodes (drift that recovers), so a
  model cannot succeed by naively mapping "any drift -> failure".
- The global `event_rate_multiplier` upsamples event frequency so one year of
  data is trainable; implemented as a Weibull scale reduction (multiplying the
  hazard by m is equivalent to dividing the scale by m^(1/k)).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MachineHistory:
    """Everything the degradation engine decides for one machine."""

    n_days: int
    # sensor name -> per-day drift in units of that sensor's noise sigma
    drift_sigma: dict[str, np.ndarray] = field(default_factory=dict)
    # warning error-code family -> per-day expected event rate (Poisson lambda)
    warn_rate: dict[str, np.ndarray] = field(default_factory=dict)
    # (day_idx, component, sudden, downtime_days)
    failures: list[tuple[int, str, bool, int]] = field(default_factory=list)
    # (day_idx, "scheduled" | "corrective", component | None)
    maintenance: list[tuple[int, str, str | None]] = field(default_factory=list)
    # True on days the machine is down (no telemetry, no scans)
    down_mask: np.ndarray | None = None
    # (start_idx, end_idx, component) for false-precursor episodes (may yield NFF tickets)
    false_episodes: list[tuple[int, int, str]] = field(default_factory=list)

    def _ensure(self, key: str, store: dict[str, np.ndarray]) -> np.ndarray:
        if key not in store:
            store[key] = np.zeros(self.n_days)
        return store[key]

    def add_drift(self, sensor: str, day_slice: slice, ramp_sigma: np.ndarray) -> None:
        arr = self._ensure(sensor, self.drift_sigma)
        seg = arr[day_slice]
        arr[day_slice] = np.maximum(seg, ramp_sigma[: len(seg)])

    def add_warn_rate(self, family: str, day_slice: slice, ramp_rate: np.ndarray) -> None:
        arr = self._ensure(family, self.warn_rate)
        seg = arr[day_slice]
        arr[day_slice] = np.maximum(seg, ramp_rate[: len(seg)])


def _conditional_weibull_remaining(
    age_years: float, shape: float, scale_years: float, rng: np.random.Generator
) -> float:
    """Sample remaining lifetime (years) given survival to `age_years`.

    For Weibull(k, lambda): S(t) = exp(-(t/lambda)^k). Conditioned on survival
    to age a, the total lifetime T satisfies
        T = lambda * ((a/lambda)^k - ln U)^(1/k),  U ~ Uniform(0,1),
    and remaining lifetime is T - a. Closed form => cheap and exact.
    """
    u = rng.uniform()
    total = scale_years * ((age_years / scale_years) ** shape - np.log(u)) ** (1.0 / shape)
    return float(total - age_years)


def simulate_machine(
    machine: dict,
    sim_days: int,
    sim_cfg: dict,
    maint_cfg: dict,
    modality_cfg: dict,
    mean_scans: float,
    rng: np.random.Generator,
) -> MachineHistory:
    """Simulate one machine's component degradation over the simulation window."""
    hist = MachineHistory(n_days=sim_days)
    hist.down_mask = np.zeros(sim_days, dtype=bool)

    multiplier = sim_cfg["event_rate_multiplier"]
    sudden_frac = sim_cfg["sudden_failure_fraction"]
    usage_factor = machine["scans_per_day"] / mean_scans  # ~1.0 fleet average
    age_at_start = machine["age_years_at_start"]

    dt_lo, dt_hi = maint_cfg["corrective_downtime_days"]

    # Pre-plan scheduled maintenance days (from a random phase, fixed cadence).
    pm_days: list[int] = []
    interval = maint_cfg["scheduled_interval_days"]
    jitter = maint_cfg["scheduled_jitter_days"]
    day = int(rng.integers(0, interval))
    while day < sim_days:
        pm_days.append(day)
        day += interval + int(rng.integers(-jitter, jitter + 1))
    pm_set = set(pm_days)
    for d in pm_days:
        hist.maintenance.append((d, "scheduled", None))

    for comp_name, comp in modality_cfg["components"].items():
        shape = comp["weibull_shape"]
        # Hazard multiplier m == scale divided by m^(1/k).
        scale = comp["weibull_scale_years"] / multiplier ** (1.0 / shape)
        usage_driven = comp.get("usage_driven", False)
        aging_per_day = (usage_factor if usage_driven else 1.0) / 365.25

        # Effective age today: usage-driven components aged with historical usage.
        age = age_at_start * (usage_factor if usage_driven else 1.0)
        # Imperfect knowledge of pre-window repairs: assume a fraction of the
        # machine's history was reset by past corrective work (keeps very old
        # machines plausible instead of guaranteeing immediate failure).
        age *= float(rng.uniform(0.35, 1.0))

        remaining = _conditional_weibull_remaining(age, shape, scale, rng)

        d = 0
        while d < sim_days:
            if d in pm_set:
                age *= 1.0 - maint_cfg["scheduled_age_improvement"]
                remaining = _conditional_weibull_remaining(age, shape, scale, rng)

            step_days = max(1, int(remaining / aging_per_day) + 1) if aging_per_day > 0 else sim_days
            fail_day = d + step_days

            # Fast-forward: does the next PM happen before the projected failure?
            next_pm = min((p for p in pm_days if d < p < fail_day), default=None)
            if next_pm is not None:
                age += aging_per_day * (next_pm - d)
                d = next_pm
                continue

            if fail_day >= sim_days:
                break  # survives the window

            # ---- Failure at fail_day ----
            sudden = rng.random() < sudden_frac
            downtime = int(rng.integers(dt_lo, dt_hi + 1))
            hist.failures.append((fail_day, comp_name, sudden, downtime))
            hist.down_mask[fail_day : min(fail_day + downtime, sim_days)] = True
            hist.maintenance.append(
                (min(fail_day + downtime, sim_days - 1), "corrective", comp_name)
            )

            if not sudden:
                w_lo, w_hi = comp["precursor"]["window_days"]
                window = int(rng.integers(w_lo, w_hi + 1))
                start = max(0, fail_day - window)
                ramp = np.linspace(0.0, 1.0, fail_day - start + 1) ** 1.5  # convex ramp
                sl = slice(start, fail_day + 1)
                for sensor, mag_sigma in comp["precursor"]["sensors"].items():
                    hist.add_drift(sensor, sl, ramp * mag_sigma)
                fam = comp["precursor"]["warn_code_family"]
                hist.add_warn_rate(fam, sl, ramp * comp["precursor"]["warn_rate_peak"])

            # Imperfect corrective repair, then continue after downtime.
            age = (age + aging_per_day * (fail_day - d)) * maint_cfg["corrective_age_reset"]
            remaining = _conditional_weibull_remaining(age, shape, scale, rng)
            d = fail_day + downtime

    # ---- False precursor episodes: drift that recovers, no failure. ----
    n_false = rng.poisson(sim_cfg["false_precursor_rate_per_year"])
    comp_names = list(modality_cfg["components"].keys())
    for _ in range(n_false):
        comp_name = comp_names[int(rng.integers(len(comp_names)))]
        comp = modality_cfg["components"][comp_name]
        length = int(rng.integers(10, 21))
        start = int(rng.integers(0, max(1, sim_days - length)))
        peak = float(rng.uniform(0.4, 0.8))
        tri = np.concatenate(
            [np.linspace(0, peak, length // 2), np.linspace(peak, 0, length - length // 2)]
        )
        sl = slice(start, start + length)
        for sensor, mag_sigma in comp["precursor"]["sensors"].items():
            hist.add_drift(sensor, sl, tri * mag_sigma)
        fam = comp["precursor"]["warn_code_family"]
        hist.add_warn_rate(fam, sl, tri * comp["precursor"]["warn_rate_peak"])
        hist.false_episodes.append((start, start + length, comp_name))

    return hist
