"""Fleet master data: machines, models, hospitals, countries, install dates."""

from __future__ import annotations

import numpy as np
import pandas as pd

# Fictional product names — deliberately NOT real product lines.
MODELS = {
    "MRI": ["Meridian 1.5T", "Meridian 3T", "Polaris 3T"],
    "CT": ["Vela 64", "Vela 128", "Aquila 256"],
    "XRAY": ["Lumen R500", "Lumen R700"],
}

REGION = {
    "DE": "EMEA", "GB": "EMEA", "FR": "EMEA", "ES": "EMEA",
    "US": "AMER", "BR": "AMER",
    "IN": "APAC", "JP": "APAC", "AU": "APAC", "CN": "APAC",
}

HOSPITAL_PREFIX = [
    "St. Mary's", "City General", "University Hospital", "Regional Medical Center",
    "Memorial", "Sacred Heart", "Central Clinic", "Metro Imaging", "Riverside",
    "Northside", "Lakeview", "Summit Health",
]


def build_fleet(cfg: dict, fm_cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Return one row per machine with static attributes."""
    fleet_cfg = cfg["fleet"]
    n = fleet_cfg["n_machines"]

    modalities = list(fleet_cfg["modality_mix"].keys())
    mod_probs = np.array(list(fleet_cfg["modality_mix"].values()), dtype=float)
    mod_probs /= mod_probs.sum()

    countries = list(fleet_cfg["countries"].keys())
    c_probs = np.array(list(fleet_cfg["countries"].values()), dtype=float)
    c_probs /= c_probs.sum()

    y0, y1 = fleet_cfg["install_year_range"]
    flaky_frac = cfg["data_quality"]["flaky_machine_fraction"]

    rows = []
    per_mod_counter: dict[str, int] = {}
    for i in range(n):
        modality = rng.choice(modalities, p=mod_probs)
        per_mod_counter[modality] = per_mod_counter.get(modality, 0) + 1
        country = rng.choice(countries, p=c_probs)
        install_year = int(rng.integers(y0, y1 + 1))
        install_date = pd.Timestamp(
            year=install_year, month=int(rng.integers(1, 13)), day=int(rng.integers(1, 28))
        )
        lo, hi = fm_cfg["modalities"][modality]["usage"]["scans_per_day"]
        rows.append(
            {
                "machine_id": f"FP-{modality}-{per_mod_counter[modality]:04d}",
                "modality": modality,
                "model": rng.choice(MODELS[modality]),
                "country": country,
                "region": REGION[country],
                "hospital_id": f"H{int(rng.integers(1, 220)):03d}",
                "hospital_name": f"{rng.choice(HOSPITAL_PREFIX)} {country}",
                "install_date": install_date,
                "scans_per_day": float(rng.uniform(lo, hi)),
                "flaky_reporter": bool(rng.random() < flaky_frac),
            }
        )
    return pd.DataFrame(rows)
