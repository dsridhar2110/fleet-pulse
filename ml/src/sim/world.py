"""Build the customer base and a growing fleet with an onboarding schedule.

The living-system story needs the fleet to *grow*: some customers are legacy
(monitored from the window's first day), others are onboarded over the 36 months
("new businesses arriving"). A machine's `commission_date` is when it enters
monitoring; its `install_date` may predate that (existing installed base joining)
or roughly coincide (a fresh install at a new site).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fleetgen.fleet_master import MODELS, REGION, HOSPITAL_PREFIX

# Customer segments → machines per site and modality lean.
SEGMENTS = {
    "imaging-centre": {"size": (1, 3), "weight": 0.45},
    "hospital":       {"size": (3, 9), "weight": 0.40},
    "IDN":            {"size": (10, 20), "weight": 0.15},  # integrated delivery network
}
IDN_NAMES = ["HealthFirst", "MedBridge", "CareNet", "Unity Health", "Vantage Medical",
             "Meridian Health", "Cornerstone Care", "Pinnacle Health", "Evergreen Medical"]


def _pick(rng, items, probs=None):
    idx = int(rng.choice(len(items), p=probs))
    return items[idx]


def build_world(
    fleet_cfg: dict, fm_cfg: dict, window_months: int, rng: np.random.Generator,
    window_start: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (customers_df, machines_df) whose machine count ≈ n_machines.

    ~60% of machines belong to legacy customers (commissioned on window day 0);
    the rest are onboarded on dates spread across the window.
    """
    fleet = fleet_cfg["fleet"]
    target = fleet["n_machines"]
    if window_start is None:
        window_start = pd.Timestamp(fleet_cfg["simulation"]["start_date"])
    window_days = int(window_months * 30.44)

    countries = list(fleet["countries"].keys())
    c_probs = np.array(list(fleet["countries"].values()), float)
    c_probs /= c_probs.sum()
    modalities = list(fleet["modality_mix"].keys())
    m_probs = np.array(list(fleet["modality_mix"].values()), float)
    m_probs /= m_probs.sum()
    seg_names = list(SEGMENTS)
    seg_probs = np.array([SEGMENTS[s]["weight"] for s in seg_names], float)
    seg_probs /= seg_probs.sum()
    y0, y1 = fleet["install_year_range"]
    flaky_frac = fleet_cfg["data_quality"]["flaky_machine_fraction"]

    customers, machines = [], []
    per_mod = {m: 0 for m in modalities}
    cust_i = 0
    n_machines = 0

    while n_machines < target:
        cust_i += 1
        seg = _pick(rng, seg_names, seg_probs)
        country = _pick(rng, countries, c_probs)
        lo, hi = SEGMENTS[seg]["size"]
        size = int(rng.integers(lo, hi + 1))
        size = min(size, target - n_machines) or 1

        # Legacy (active day 0) vs onboarded-during-window.
        if rng.random() < 0.62:
            onboarded = window_start - pd.Timedelta(days=int(rng.integers(200, 1500)))
            commission_day = 0
        else:
            commission_day = int(rng.integers(15, max(16, window_days - 90)))
            onboarded = window_start + pd.Timedelta(days=commission_day)

        if seg == "IDN":
            name = f"{_pick(rng, IDN_NAMES)} ({country})"
        elif seg == "hospital":
            name = f"{_pick(rng, HOSPITAL_PREFIX)} {country}"
        else:
            name = f"{_pick(rng, ['Bright', 'Clarity', 'Insight', 'Apex', 'Vista', 'Precision'])} " \
                   f"Imaging {country}-{cust_i:03d}"
        cid = f"CUST-{cust_i:03d}"
        customers.append({
            "customer_id": cid, "name": name, "country": country, "region": REGION[country],
            "segment": seg, "onboarded_date": onboarded.date(),
        })

        for _ in range(size):
            modality = _pick(rng, modalities, m_probs)
            per_mod[modality] += 1
            commission_date = window_start + pd.Timedelta(days=commission_day) \
                if commission_day > 0 else window_start
            # Legacy sites: old installed base. New sites: recent installs.
            if commission_day == 0:
                iy = int(rng.integers(y0, y1 + 1))
                install_date = pd.Timestamp(iy, int(rng.integers(1, 13)), int(rng.integers(1, 28)))
            else:
                back = int(rng.integers(0, 730))  # installed up to ~2y before joining
                install_date = commission_date - pd.Timedelta(days=back)
            lo_s, hi_s = fm_cfg["modalities"][modality]["usage"]["scans_per_day"]
            machines.append({
                "machine_id": f"FP-{modality}-{per_mod[modality]:04d}",
                "customer_id": cid, "modality": modality, "model": _pick(rng, MODELS[modality]),
                "country": country, "region": REGION[country],
                "hospital_name": name,
                "install_date": install_date.date(),
                "commission_date": commission_date.date(),
                "commission_day": max(0, commission_day),
                "scans_per_day": float(rng.uniform(lo_s, hi_s)),
                "flaky_reporter": bool(rng.random() < flaky_frac),
                "status": "active",
            })
            n_machines += 1
            if n_machines >= target:
                break

    return pd.DataFrame(customers), pd.DataFrame(machines)
