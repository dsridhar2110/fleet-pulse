"""Export model + data artifacts to JSON the Next.js product consumes.

Writes into web/public/data/:
  fleet.json                 fleet summary + one row per machine (latest week)
  metrics.json               evaluation metrics + baseline comparison
  drivers_global.json        global SHAP driver importance (model page)
  machines/<id>.json         per-machine detail (telemetry, tickets, risk, drivers)

Also mirrors any side-artifacts already produced by their own stages
(anomaly_metrics.json from the Keras autoencoder, retrieval_metrics.json from
the copilot index), so a fresh clone can rebuild web/public/data in one command
instead of remembering which notebook wrote which file.

Everything is precomputed and static — the deployed app never runs Spark,
Python, or a model. Values are rounded to keep the payload small.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
ART = ROOT / "data/app"
WEB = ROOT.parent / "web" / "public" / "data"

# Display severity bands on calibrated 7-day failure risk. These are UX tiers
# for triage color, distinct from the cost-optimal DISPATCH threshold (~0.01):
# at this fleet's ~1.3% base rate, >=20% risk is ~15x baseline (critical),
# 5-20% is elevated (watch), below is healthy.
CRIT, WATCH = 0.20, 0.05
KEY_SENSORS = {
    "MRI": ["helium_level", "compressor_temp", "vibration_rms", "scans_count"],
    "CT": ["tube_current_var", "tube_temp", "gantry_vibration", "scans_count"],
    "XRAY": ["filament_current", "voltage_ripple", "tube_temp", "scans_count"],
}


def status_of(risk: float) -> str:
    return "critical" if risk >= CRIT else "watch" if risk >= WATCH else "healthy"


def r(x, n=3):
    return None if pd.isna(x) else round(float(x), n)


def main() -> None:
    (WEB / "machines").mkdir(parents=True, exist_ok=True)

    fleet = pd.read_parquet(RAW / "fleet_master.parquet")
    scores = pd.read_parquet(ART / "scores.parquet")
    scores["date"] = pd.to_datetime(scores["date"])
    drivers = pd.read_parquet(ART / "shap_per_machine.parquet")
    failures = pd.read_parquet(RAW / "failures.parquet")
    tickets = pd.read_parquet(RAW / "tickets.parquet")
    maint = pd.read_parquet(RAW / "maintenance.parquet")
    metrics = json.loads((ART / "metrics.json").read_text())
    global_imp = pd.read_parquet(ART / "shap_global.parquet")

    # "Current week" = last week with a COMPLETE 7-day forward window inside the
    # simulation. The final scoring week's window runs past the data end, so it
    # is truncated (almost nothing is genuinely pre-failure) — exclude it.
    max_date = scores["date"].max()
    full_weeks = scores.loc[scores["date"] <= max_date - pd.Timedelta(days=7), "date"]
    latest_date = full_weeks.max()
    latest = scores[scores["date"] == latest_date].set_index("machine_id")

    top_driver = (
        drivers[drivers["rank"] == 1].set_index("machine_id")["driver"].to_dict()
    )

    # ---- fleet.json ----
    rows = []
    for _, m in fleet.iterrows():
        mid = m["machine_id"]
        risk = float(latest.at[mid, "risk_calibrated"]) if mid in latest.index else 0.0
        rows.append(
            {
                "id": mid,
                "modality": m["modality"],
                "model": m["model"],
                "country": m["country"],
                "region": m["region"],
                "hospital": m["hospital_name"],
                "risk": round(risk, 3),
                "status": status_of(risk),
                "likelyIssue": top_driver.get(mid, "—") if status_of(risk) != "healthy" else "—",
                "ageYears": round(float((latest_date - m["install_date"]).days / 365.25), 1),
            }
        )
    rows.sort(key=lambda x: x["risk"], reverse=True)

    counts = {s: sum(1 for x in rows if x["status"] == s) for s in ("critical", "watch", "healthy")}
    fleet_json = {
        "asOf": latest_date.strftime("%Y-%m-%d"),
        "summary": {
            "machines": len(rows),
            "critical": counts["critical"],
            "watch": counts["watch"],
            "healthy": counts["healthy"],
            "modalities": sorted(fleet["modality"].unique().tolist()),
            "countries": sorted(fleet["country"].unique().tolist()),
        },
        "machines": rows,
    }
    (WEB / "fleet.json").write_text(json.dumps(fleet_json, separators=(",", ":")))

    # ---- metrics.json + drivers_global.json ----
    (WEB / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (WEB / "drivers_global.json").write_text(
        global_imp.assign(importance=global_imp["importance"].round(4)).to_json(orient="records")
    )

    # ---- per-machine detail ----
    tel = pd.read_parquet(RAW / "telemetry")
    tel["date"] = pd.to_datetime(tel["date"])
    tickets["open_date"] = pd.to_datetime(tickets["open_date"])
    failures["failure_date"] = pd.to_datetime(failures["failure_date"])

    tel_by_machine = dict(tuple(tel.groupby("machine_id")))
    tick_by_machine = dict(tuple(tickets.groupby("machine_id")))
    fail_by_machine = dict(tuple(failures.groupby("machine_id")))
    score_by_machine = dict(tuple(scores.groupby("machine_id")))
    drv_by_machine = dict(tuple(drivers.groupby("machine_id")))
    maint["date"] = pd.to_datetime(maint["date"])
    maint_by_machine = dict(tuple(maint.groupby("machine_id")))

    for _, m in fleet.iterrows():
        mid = m["machine_id"]
        sensors = KEY_SENSORS[m["modality"]]
        mt = tel_by_machine.get(mid, pd.DataFrame())

        # Telemetry: pivot key sensors, downsample to every 2nd day, round.
        series = []
        if not mt.empty:
            wide = (
                mt[mt["sensor"].isin(sensors)]
                .pivot_table(index="date", columns="sensor", values="value")
                .sort_index()
                .iloc[::2]
            )
            for dt, row in wide.iterrows():
                point = {"d": dt.strftime("%Y-%m-%d")}
                for s in sensors:
                    if s in row:
                        point[s] = r(row[s], 2)
                series.append(point)

        risk_hist = [
            {"d": d.strftime("%Y-%m-%d"), "risk": round(float(v), 3)}
            for d, v in score_by_machine.get(mid, pd.DataFrame(columns=["date", "risk_calibrated"]))
            .sort_values("date")[["date", "risk_calibrated"]]
            .itertuples(index=False)
        ] if mid in score_by_machine else []

        tk = tick_by_machine.get(mid, pd.DataFrame())
        ticket_list = [
            {
                "date": t.open_date.strftime("%Y-%m-%d"),
                "type": t.ticket_type,
                "component": t.component,
                "part": t.part_replaced,
                "engineer": t.engineer_id,
                "note": t.note_text,
            }
            for t in tk.sort_values("open_date").itertuples(index=False)
        ] if not tk.empty else []

        fl = fail_by_machine.get(mid, pd.DataFrame())
        failure_marks = [
            {"date": f.failure_date.strftime("%Y-%m-%d"), "component": f.component, "sudden": bool(f.sudden)}
            for f in fl.itertuples(index=False)
        ] if not fl.empty else []

        mm = maint_by_machine.get(mid, pd.DataFrame())
        maint_marks = [
            {"date": x.date.strftime("%Y-%m-%d"), "type": x.maintenance_type}
            for x in mm.itertuples(index=False)
        ] if not mm.empty else []

        dv = drv_by_machine.get(mid, pd.DataFrame())
        driver_list = [
            {"driver": d.driver, "contribution": round(float(d.contribution), 4)}
            for d in dv.sort_values("rank").itertuples(index=False)
        ] if not dv.empty else []

        risk_now = float(latest.at[mid, "risk_calibrated"]) if mid in latest.index else 0.0
        detail = {
            "id": mid,
            "modality": m["modality"],
            "model": m["model"],
            "country": m["country"],
            "region": m["region"],
            "hospital": m["hospital_name"],
            "installDate": m["install_date"].strftime("%Y-%m-%d"),
            "ageYears": round(float((latest_date - m["install_date"]).days / 365.25), 1),
            "risk": round(risk_now, 3),
            "status": status_of(risk_now),
            "sensors": sensors,
            "telemetry": series,
            "riskHistory": risk_hist,
            "tickets": ticket_list,
            "failures": failure_marks,
            "maintenance": maint_marks,
            "drivers": driver_list,
        }
        (WEB / "machines" / f"{mid}.json").write_text(json.dumps(detail, separators=(",", ":")))

    # Mirror artifacts written by other stages (autoencoder, copilot index).
    for name in ("anomaly_metrics.json", "retrieval_metrics.json", "impact.json"):
        src = ART / name
        if src.exists():
            (WEB / name).write_text(src.read_text())
        else:
            print(f"  note: {name} not found in data/app — run its stage to include it")

    total_mb = sum(f.stat().st_size for f in WEB.rglob("*.json")) / 1e6
    print(f"as-of {latest_date.date()} | machines {len(rows)} "
          f"(crit {counts['critical']}, watch {counts['watch']}, healthy {counts['healthy']})")
    print(f"wrote {len(list((WEB / 'machines').glob('*.json')))} machine files | total {total_mb:.1f} MB -> {WEB}")


if __name__ == "__main__":
    main()
