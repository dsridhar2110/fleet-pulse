"""Resumable daily physics: latent state + one-day step for a single machine.

Design mirror of `fleetgen.degradation` / `.telemetry` / `.events`, re-expressed
as a state machine. The invariant that makes a daily system possible: each
component's *next* failure is scheduled the moment its clock (re)starts —
at commissioning, after a PM, or after a repair. Because the upcoming failure
day and its precursor window are known in advance, the precursor drift for any
given day can be emitted *forward* instead of filled in retroactively.

State is plain-dataclass and JSON-serialisable (see `to_dict`/`from_dict`) so it
round-trips through a `machine_state` row in Postgres between days.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from fleetgen.degradation import _conditional_weibull_remaining
from .common import USAGE_COUPLED

_BIG = 10**9  # "no failure scheduled within any horizon we care about"


# --------------------------------------------------------------------------- #
# Latent state
# --------------------------------------------------------------------------- #
@dataclass
class ComponentState:
    name: str
    age_years: float           # effective age (usage-adjusted)
    aging_per_day: float       # effective-years accrued per calendar day
    fail_day: int              # absolute world-day of the next projected failure (_BIG = none)
    sudden: bool               # is that scheduled failure sudden (no precursor)?
    precursor_start: int       # absolute world-day the precursor drift begins (_BIG if sudden)
    downtime: int              # downtime days for the scheduled failure


@dataclass
class FalseEpisode:
    """Drift that looks like degradation but recovers without a failure."""
    component: str
    start: int
    end: int
    peak: float


@dataclass
class MachineSimState:
    machine_id: str
    modality: str
    scans_per_day: float
    usage_factor: float        # scans_per_day / modality-mean (usage intensity)
    flaky_reporter: bool
    calib: dict[str, float]                       # per-sensor calibration offset (drawn once)
    components: dict[str, ComponentState]
    next_pm_day: int
    down_until_day: int                           # -1 when up; else world-day service resumes
    pending_repair_comp: str | None = None        # component whose corrective visit closes on resume
    false_episodes: list[FalseEpisode] = field(default_factory=list)
    rng_state: dict | None = None                 # numpy bit-generator state (resumability)

    # -- serialisation ------------------------------------------------------ #
    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MachineSimState":
        comps = {k: ComponentState(**v) for k, v in d["components"].items()}
        eps = [FalseEpisode(**e) for e in d.get("false_episodes", [])]
        rest = {k: v for k, v in d.items() if k not in ("components", "false_episodes")}
        return cls(components=comps, false_episodes=eps, **rest)


# --------------------------------------------------------------------------- #
# Scheduling helpers
# --------------------------------------------------------------------------- #
def _weibull_scale(comp_cfg: dict, sim_cfg: dict) -> float:
    shape = comp_cfg["weibull_shape"]
    return comp_cfg["weibull_scale_years"] / sim_cfg["event_rate_multiplier"] ** (1.0 / shape)


def _schedule_failure(
    cs: ComponentState, comp_cfg: dict, sim_cfg: dict, maint_cfg: dict,
    ref_day: int, rng: np.random.Generator,
) -> None:
    """(Re)project this component's next failure from `ref_day`, given its age."""
    shape = comp_cfg["weibull_shape"]
    scale = _weibull_scale(comp_cfg, sim_cfg)
    remaining = _conditional_weibull_remaining(cs.age_years, shape, scale, rng)
    if cs.aging_per_day <= 0:
        cs.fail_day = _BIG
        return
    days_ahead = max(1, int(remaining / cs.aging_per_day) + 1)
    cs.fail_day = ref_day + days_ahead
    cs.sudden = bool(rng.random() < sim_cfg["sudden_failure_fraction"])
    w_lo, w_hi = comp_cfg["precursor"]["window_days"]
    window = int(rng.integers(w_lo, w_hi + 1))
    cs.precursor_start = _BIG if cs.sudden else cs.fail_day - window
    dt_lo, dt_hi = maint_cfg["corrective_downtime_days"]
    cs.downtime = int(rng.integers(dt_lo, dt_hi + 1))


def _next_pm(day: int, maint_cfg: dict, rng: np.random.Generator) -> int:
    interval = maint_cfg["scheduled_interval_days"]
    jitter = maint_cfg["scheduled_jitter_days"]
    return day + interval + int(rng.integers(-jitter, jitter + 1))


def init_machine_state(
    machine: dict, commission_day: int, age_years_at_commission: float,
    fm_cfg: dict, fleet_cfg: dict, mean_scans: float, rng: np.random.Generator,
) -> MachineSimState:
    """Build latent state for a machine entering service at `commission_day`."""
    modality = machine["modality"]
    modality_cfg = fm_cfg["modalities"][modality]
    sim_cfg, maint_cfg = fleet_cfg["simulation"], fleet_cfg["maintenance"]
    dq_cfg = fleet_cfg["data_quality"]
    usage_factor = machine["scans_per_day"] / mean_scans

    calib = {
        s: float(rng.normal(0.0, dq_cfg["calibration_offset_sigma"] * c["sigma"]))
        for s, c in modality_cfg["sensors"].items()
    }

    components: dict[str, ComponentState] = {}
    for name, comp_cfg in modality_cfg["components"].items():
        usage_driven = comp_cfg.get("usage_driven", False)
        aging_per_day = (usage_factor if usage_driven else 1.0) / 365.25
        # Effective age at commissioning, with imperfect knowledge of past repairs.
        age = age_years_at_commission * (usage_factor if usage_driven else 1.0)
        age *= float(rng.uniform(0.35, 1.0))
        cs = ComponentState(
            name=name, age_years=age, aging_per_day=aging_per_day,
            fail_day=_BIG, sudden=False, precursor_start=_BIG, downtime=0,
        )
        _schedule_failure(cs, comp_cfg, sim_cfg, maint_cfg, commission_day, rng)
        components[name] = cs

    state = MachineSimState(
        machine_id=machine["machine_id"], modality=modality,
        scans_per_day=float(machine["scans_per_day"]), usage_factor=usage_factor,
        flaky_reporter=bool(machine["flaky_reporter"]), calib=calib,
        components=components,
        next_pm_day=commission_day + int(rng.integers(0, maint_cfg["scheduled_interval_days"])),
        down_until_day=-1,
    )
    return state


# --------------------------------------------------------------------------- #
# One-day step
# --------------------------------------------------------------------------- #
def _codes(family: str, base: int, n: int = 3) -> list[str]:
    return [f"{family}-{base + j}" for j in range(n)]


def step_machine_day(
    state: MachineSimState, day: int, date, fm_cfg: dict, fleet_cfg: dict,
    rng: np.random.Generator,
) -> dict:
    """Advance one machine by a single day; mutate `state`; return emitted rows.

    Returns a dict with keys: telemetry, errors, failures, maintenance, tickets
    (each a list of row-dicts, possibly empty).
    """
    modality_cfg = fm_cfg["modalities"][state.modality]
    sim_cfg = fleet_cfg["simulation"]
    maint_cfg = fleet_cfg["maintenance"]
    dq_cfg = fleet_cfg["data_quality"]
    error_cfg = fm_cfg["error_codes"]
    sensors_cfg = modality_cfg["sensors"]

    mid = state.machine_id
    out = {"telemetry": [], "errors": [], "failures": [], "maintenance": [], "tickets": []}
    down = day < state.down_until_day

    # --- 0. Service resumes (corrective visit closes) ----------------------- #
    if day == state.down_until_day:
        out["maintenance"].append(
            {"machine_id": mid, "date": date, "maintenance_type": "corrective",
             "component": state.pending_repair_comp}  # set when the failure fired
        )
        state.down_until_day = -1
        state.pending_repair_comp = None
        down = False

    # --- 1. Scheduled preventive maintenance -------------------------------- #
    if not down and day == state.next_pm_day:
        out["maintenance"].append(
            {"machine_id": mid, "date": date, "maintenance_type": "scheduled", "component": None})
        out["tickets"].append(_pm_ticket(mid, date, rng))
        for name, cs in state.components.items():
            cs.age_years *= 1.0 - maint_cfg["scheduled_age_improvement"]
            _schedule_failure(cs, modality_cfg["components"][name], sim_cfg, maint_cfg, day, rng)
        state.next_pm_day = _next_pm(day, maint_cfg, rng)

    # --- 2. Failures -------------------------------------------------------- #
    if not down:
        for name, cs in state.components.items():
            if cs.fail_day == day and state.down_until_day < 0:
                downtime = cs.downtime
                repair_day = day + downtime
                out["failures"].append(
                    {"machine_id": mid, "failure_date": date, "component": name,
                     "sudden": cs.sudden, "downtime_days": downtime})
                # critical burst today
                fam = modality_cfg["components"][name]["precursor"]["warn_code_family"]
                for _ in range(error_cfg["critical_on_failure"]):
                    out["errors"].append(
                        {"machine_id": mid, "date": date, "error_code": f"{fam}-900",
                         "family": fam, "severity": "critical"})
                out["tickets"].append(
                    _corrective_ticket(mid, date, repair_day, name, cs.sudden, downtime,
                                       modality_cfg, rng))
                state.down_until_day = repair_day
                state.pending_repair_comp = name
                # imperfect repair, reschedule from repair completion
                cs.age_years *= maint_cfg["corrective_age_reset"]
                _schedule_failure(cs, modality_cfg["components"][name], sim_cfg, maint_cfg,
                                  repair_day, rng)
                down = True  # only one failure-induced outage at a time

    # --- 3. Maybe start a false-precursor episode --------------------------- #
    if rng.random() < sim_cfg["false_precursor_rate_per_year"] / 365.25:
        comp = list(modality_cfg["components"].keys())[
            int(rng.integers(len(modality_cfg["components"])))]
        length = int(rng.integers(10, 21))
        state.false_episodes.append(
            FalseEpisode(component=comp, start=day, end=day + length,
                         peak=float(rng.uniform(0.4, 0.8))))

    # --- 4. Drift + warn-rate for today ------------------------------------- #
    drift_sigma: dict[str, float] = {}
    warn_rate: dict[str, float] = {}

    def _bump(store, key, val):
        if val > store.get(key, 0.0):
            store[key] = val

    for name, cs in state.components.items():
        comp_cfg = modality_cfg["components"][name]
        if not cs.sudden and cs.precursor_start <= day <= cs.fail_day and cs.fail_day < _BIG:
            span = max(1, cs.fail_day - cs.precursor_start)
            ramp = ((day - cs.precursor_start) / span) ** 1.5
            for sensor, mag in comp_cfg["precursor"]["sensors"].items():
                _bump(drift_sigma, sensor, ramp * mag)
            _bump(warn_rate, comp_cfg["precursor"]["warn_code_family"],
                  ramp * comp_cfg["precursor"]["warn_rate_peak"])

    still_active = []
    for ep in state.false_episodes:
        if ep.end < day:
            continue
        still_active.append(ep)
        comp_cfg = modality_cfg["components"][ep.component]
        length = ep.end - ep.start
        half = length // 2
        pos = day - ep.start
        if 0 <= pos <= length:
            tri = (pos / half * ep.peak) if pos <= half else (
                ep.peak * (1 - (pos - half) / max(1, length - half)))
            tri = max(0.0, tri)
            for sensor, mag in comp_cfg["precursor"]["sensors"].items():
                _bump(drift_sigma, sensor, tri * mag)
            _bump(warn_rate, comp_cfg["precursor"]["warn_code_family"],
                  tri * comp_cfg["precursor"]["warn_rate_peak"])
        if day == ep.end and rng.random() < 0.5:
            out["tickets"].append(_nff_ticket(mid, date, ep.component, rng))
    state.false_episodes = still_active

    if down:
        return out  # powered down: no telemetry, no error events

    # --- 5. Telemetry ------------------------------------------------------- #
    weekend = date.dayofweek >= 5
    lam = state.scans_per_day * (0.55 if weekend else 1.0)
    scans = float(rng.poisson(lam))
    miss_rate = dq_cfg["flaky_missing_day_rate"] if state.flaky_reporter else dq_cfg["missing_day_rate"]
    missing = rng.random() < miss_rate

    if not missing:
        usage_ratio = scans / state.scans_per_day if state.scans_per_day > 0 else 1.0
        for sensor, s_cfg in sensors_cfg.items():
            sigma = s_cfg["sigma"]
            val = (s_cfg["baseline"] + state.calib.get(sensor, 0.0)
                   + float(rng.normal(0.0, sigma))
                   + s_cfg["drift_sign"] * drift_sigma.get(sensor, 0.0) * sigma)
            if sensor in USAGE_COUPLED:
                val += 0.3 * sigma * (usage_ratio - 1.0)
            out["telemetry"].append(
                {"machine_id": mid, "date": date, "sensor": sensor, "value": val,
                 "modality": state.modality})
        out["telemetry"].append(
            {"machine_id": mid, "date": date, "sensor": "scans_count", "value": scans,
             "modality": state.modality})

    # --- 6. Error events ---------------------------------------------------- #
    for fam, f_cfg in error_cfg["benign_families"].items():
        c = int(rng.poisson(f_cfg["rate_per_day"]))
        for _ in range(c):
            out["errors"].append(
                {"machine_id": mid, "date": date,
                 "error_code": str(rng.choice(_codes(fam, 100))), "family": fam,
                 "severity": "info"})
    for fam, rate in warn_rate.items():
        if rate <= 0:
            continue
        c = int(rng.poisson(rate))
        for _ in range(c):
            out["errors"].append(
                {"machine_id": mid, "date": date,
                 "error_code": str(rng.choice(_codes(fam, 400))), "family": fam,
                 "severity": "warning"})

    # --- 7. Age components -------------------------------------------------- #
    for cs in state.components.values():
        cs.age_years += cs.aging_per_day

    return out


# --------------------------------------------------------------------------- #
# Ticket templates (mirrors fleetgen.tickets vocabulary)
# --------------------------------------------------------------------------- #
_SYMPTOMS = {
    "CRYO": ["He level low", "helium lvl dropping fast", "cryo issue reported by site",
             "compressor running hot", "boil-off rate above spec"],
    "GRAD": ["gradient temp unstable", "grad coil overheating", "image artifacts, grad noise",
             "coil cooling loop pressure low"],
    "RF": ["rf power fluctuating", "RF amp fault intermittent", "SNR degraded, rf suspected"],
    "TUBE": ["arcing events increasing", "tube current unstable", "tube nearing EOL",
             "spits observed during exposure", "xray tube arc warnings"],
    "DET": ["detector noise high", "det module dropout", "image noise complaint from site"],
    "GANTRY": ["gantry vibration high", "bearing noise during rotation", "rotation speed unstable"],
    "PWR": ["voltage ripple above limit", "generator output unstable", "power fluctuation at site"],
}
_ACTIONS = {
    "CRYO": ["replaced cold head assembly", "swapped compressor adsorber", "recharged helium + new seal kit"],
    "GRAD": ["replaced gradient amplifier board", "flushed coil cooling loop"],
    "RF": ["swapped RF amplifier module", "replaced RF fuse set, recal ok"],
    "TUBE": ["tube replaced, recalibrated", "new HV cable set + oil cooling unit", "tube insert swap done"],
    "DET": ["replaced detector module", "DAS board swap, pixel map redone"],
    "GANTRY": ["main bearing replaced", "slip ring brushes swapped, cleaned"],
    "PWR": ["HV generator board replaced", "capacitor bank swapped"],
}
_CLOSERS = ["system back to spec.", "QA passed, released to clinical use.", "site confirmed ok.",
            "monitoring for 48h.", "customer informed."]
_PM_NOTES = ["routine PM done, all checks passed", "preventive maint completed, minor adjustments",
             "PM visit - filters, cal check, no issues", "scheduled service done. nothing abnormal"]
_NFF_NOTES = ["site reported alerts, no fault found on inspection", "checked logs, values back in range. NFF",
              "intermittent drift, could not reproduce. monitoring", "no fault found, sensor recal done as precaution"]


def _rough(text: str, rng: np.random.Generator) -> str:
    if rng.random() < 0.3:
        text = text.lower()
    if rng.random() < 0.2:
        text += " (esc L2)" if rng.random() < 0.5 else " ref prev tkt"
    return text


def _corrective_ticket(mid, date, repair_day, comp, sudden, downtime, modality_cfg, rng):
    fam = modality_cfg["components"][comp]["precursor"]["warn_code_family"]
    part = str(rng.choice(modality_cfg["components"][comp]["parts"]))
    note = f"{_rough(str(rng.choice(_SYMPTOMS[fam])), rng)}. " \
           f"{_rough(str(rng.choice(_ACTIONS[fam])), rng)}. {rng.choice(_CLOSERS)}"
    if sudden:
        note = f"sudden failure, no prior alerts. {note}"
    return {"machine_id": mid, "open_date": date, "close_date": None, "repair_day": repair_day,
            "ticket_type": "corrective", "component": comp, "part_replaced": part,
            "downtime_days": downtime, "note_text": note}


def _pm_ticket(mid, date, rng):
    return {"machine_id": mid, "open_date": date, "close_date": date, "repair_day": None,
            "ticket_type": "preventive", "component": None, "part_replaced": None,
            "downtime_days": 0, "note_text": _rough(str(rng.choice(_PM_NOTES)), rng)}


def _nff_ticket(mid, date, comp, rng):
    return {"machine_id": mid, "open_date": date, "close_date": date, "repair_day": None,
            "ticket_type": "no_fault_found", "component": comp, "part_replaced": None,
            "downtime_days": 0, "note_text": _rough(str(rng.choice(_NFF_NOTES)), rng)}
