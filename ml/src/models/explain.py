"""SHAP explanations: global driver importance + per-machine top drivers.

Discipline (stated in the case study): SHAP explains the MODEL, not the
physics. On synthetic data the two align by construction; on real data that
alignment is exactly what you validate with service engineers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from .train_xgb import CATEGORICAL, FORBIDDEN

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data" / "app"

# Human-readable labels for the sensor/feature families (worklist "likely issue").
FEATURE_LABEL = {
    "helium_level": "Helium / cold head",
    "compressor_temp": "Cooling / compressor",
    "gradient_temp": "Gradient coil",
    "rf_power_var": "RF amplifier",
    "vibration_rms": "Vibration / bearing",
    "chiller_flow": "Chiller flow",
    "tube_current_var": "X-ray tube",
    "tube_temp": "X-ray tube (thermal)",
    "detector_noise": "Detector array",
    "gantry_vibration": "Gantry bearing",
    "cooling_margin": "Cooling margin",
    "filament_current": "Tube filament",
    "voltage_ripple": "Generator / power",
    "err_warn": "Warning-code burst",
    "err_crit": "Critical-code burst",
    "warn_burst": "Warning-code burst",
    "age_years": "Machine age",
    "days_since_pm": "Overdue maintenance",
    "days_since_cm": "Recent repair history",
    "scans": "Usage intensity",
}


def base_family(col: str) -> str:
    for key, label in FEATURE_LABEL.items():
        if col.startswith(key):
            return label
    return col


def main() -> None:
    df = pd.read_parquet(ROOT / "data/features/labeled.parquet")
    df["date"] = pd.to_datetime(df["date"])
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")

    model = xgb.XGBClassifier(enable_categorical=True)
    model.load_model(ART / "xgb_model.json")
    feature_cols = [c for c in df.columns if c not in FORBIDDEN]

    explainer = shap.TreeExplainer(model)
    X = df[feature_cols]
    sv = explainer.shap_values(X)
    shap_df = pd.DataFrame(sv, columns=feature_cols, index=df.index)

    # ---- Global importance: mean |SHAP| aggregated to human families ----
    mean_abs = shap_df.abs().mean().sort_values(ascending=False)
    fam = {}
    for col, val in mean_abs.items():
        fam[base_family(col)] = fam.get(base_family(col), 0.0) + float(val)
    global_imp = (
        pd.Series(fam).sort_values(ascending=False).head(12).rename_axis("driver").reset_index(name="importance")
    )
    global_imp.to_parquet(ART / "shap_global.parquet", index=False)

    # ---- Per-machine top drivers on the LATEST scoring date per machine ----
    latest_idx = df.groupby("machine_id")["date"].idxmax()
    rows = []
    for idx in latest_idx:
        machine = df.at[idx, "machine_id"]
        contrib = shap_df.loc[idx]
        # Only positive contributions = things pushing risk UP.
        pos = contrib[contrib > 0]
        agg: dict[str, float] = {}
        for col, val in pos.items():
            agg[base_family(col)] = agg.get(base_family(col), 0.0) + float(val)
        top = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:5]
        for rank, (driver, val) in enumerate(top, 1):
            rows.append({"machine_id": machine, "rank": rank, "driver": driver, "contribution": val})
    per_machine = pd.DataFrame(rows)
    per_machine.to_parquet(ART / "shap_per_machine.parquet", index=False)

    print(f"global drivers: {len(global_imp)} | per-machine driver rows: {len(per_machine)}")
    print("top global drivers:", ", ".join(global_imp["driver"].head(6)))
    print(f"artifacts -> {ART}")


if __name__ == "__main__":
    main()
