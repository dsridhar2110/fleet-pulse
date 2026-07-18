"""Feature engineering over the live Postgres store (pandas path).

The v1 pipeline builds features in PySpark over Parquet — kept as the offline/
batch demonstration. For the *daily* living system, features are computed in
pandas straight from Neon: it's 500 machines, so Spark is unnecessary here and a
pure-Python job is what actually runs in the daily cron.

Two entry points:
  * `compute_panel(frames)` — a per-machine-per-day feature panel (rolling stats,
    trends, error bursts, maintenance/age) computed once over all history.
  * `features_asof(panel, as_of)` — the feature row per machine as of a date,
    used both to assemble a training set (many as-of dates) and to score today.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

ROLL = (7, 14, 30)


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
def load_frames(engine: Engine, up_to: str | None = None,
                since: str | None = None) -> dict[str, pd.DataFrame]:
    """Pull the frames needed for features. Error events are aggregated to daily
    counts in SQL (keeps ~1M event rows off the wire).

    `up_to` caps the window (as-of scoring); `since` floors it — pass both for a
    fast trailing-window pull (the daily tick only needs ~120 days of history)."""
    conds, fconds, params = [], [], {}
    if up_to:
        conds.append("date <= :up_to"); fconds.append("failure_date <= :up_to"); params["up_to"] = up_to
    if since:
        conds.append("date >= :since"); fconds.append("failure_date >= :since"); params["since"] = since
    clause = ("WHERE " + " AND ".join(conds)) if conds else ""
    fclause = ("WHERE " + " AND ".join(fconds)) if fconds else ""
    with engine.connect() as c:
        machines = pd.read_sql(text("SELECT * FROM machines"), c)
        tel = pd.read_sql(text(f"SELECT machine_id, date, modality, scans_count, readings "
                               f"FROM telemetry_daily {clause}"), c, params=params)
        err = pd.read_sql(text(
            f"SELECT machine_id, date, "
            f"SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) AS warn, "
            f"SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS crit, "
            f"COUNT(*) AS total FROM error_events {clause} GROUP BY machine_id, date"), c,
            params=params)
        maint = pd.read_sql(text(f"SELECT machine_id, date, maintenance_type "
                                 f"FROM maintenance {clause}"), c, params=params)
        fails = pd.read_sql(text(f"SELECT machine_id, failure_date, component, sudden "
                                 f"FROM failures {fclause}"), c, params=params)
    for df, col in [(tel, "date"), (err, "date"), (maint, "date"), (fails, "failure_date")]:
        df[col] = pd.to_datetime(df[col])
    return {"machines": machines, "telemetry": tel, "errors": err,
            "maintenance": maint, "failures": fails}


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
def _expand_readings(tel: pd.DataFrame) -> pd.DataFrame:
    """JSONB readings → one column per sensor (psycopg2 returns dicts already)."""
    readings = pd.json_normalize(tel["readings"]).set_index(tel.index)
    out = pd.concat([tel[["machine_id", "date", "modality", "scans_count"]], readings], axis=1)
    return out


def compute_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per-machine-per-day feature panel over all history."""
    tel = _expand_readings(frames["telemetry"]).sort_values(["machine_id", "date"])
    sensor_cols = [c for c in tel.columns
                   if c not in ("machine_id", "date", "modality", "scans_count")]

    # Reindex each machine to a continuous daily grid so rolling windows mean days.
    panels = []
    err = frames["errors"].set_index(["machine_id", "date"]).sort_index()
    maint = frames["maintenance"]
    pm = maint[maint.maintenance_type == "scheduled"].groupby("machine_id")["date"]
    cm = maint[maint.maintenance_type == "corrective"].groupby("machine_id")["date"]

    for mid, g in tel.groupby("machine_id"):
        g = g.set_index("date").sort_index()
        idx = pd.date_range(g.index.min(), g.index.max(), freq="D")
        g = g.reindex(idx)
        g["machine_id"] = mid
        g["modality"] = g["modality"].ffill().bfill()
        feat = {"machine_id": mid, "date": idx}

        # sensor rolling stats + trend + z-vs-baseline
        base_win = 30
        for s in sensor_cols:
            if s not in g:
                continue
            v = g[s].astype(float)
            baseline_mu = v.rolling(base_win, min_periods=5).mean().shift(7)
            baseline_sd = v.rolling(base_win, min_periods=5).std().shift(7).replace(0, np.nan)
            feat[f"{s}_last"] = v.ffill()
            feat[f"{s}_z"] = (v - baseline_mu) / baseline_sd
            for w in ROLL:
                rm = v.rolling(w, min_periods=max(2, w // 3)).mean()
                feat[f"{s}_mean{w}"] = rm
                feat[f"{s}_std{w}"] = v.rolling(w, min_periods=max(2, w // 3)).std()
            feat[f"{s}_trend14"] = (v.rolling(7, min_periods=2).mean()
                                    - v.rolling(7, min_periods=2).mean().shift(7))

        # usage
        sc = g["scans_count"].astype(float)
        feat["scans_mean7"] = sc.rolling(7, min_periods=2).mean()
        feat["scans_mean30"] = sc.rolling(30, min_periods=5).mean()
        feat["missing_frac14"] = g[sensor_cols[0]].isna().rolling(14, min_periods=5).mean() \
            if sensor_cols else 0.0

        pf = pd.DataFrame(feat).set_index("date")

        # error-burst features
        if mid in err.index.get_level_values(0):
            e = err.loc[mid].reindex(idx).fillna(0.0)
            for w in ROLL:
                pf[f"warn_sum{w}"] = e["warn"].rolling(w, min_periods=1).sum()
                pf[f"err_sum{w}"] = e["total"].rolling(w, min_periods=1).sum()
            pf["crit_sum7"] = e["crit"].rolling(7, min_periods=1).sum()
        else:
            for w in ROLL:
                pf[f"warn_sum{w}"] = 0.0
                pf[f"err_sum{w}"] = 0.0
            pf["crit_sum7"] = 0.0

        # days-since maintenance
        pf["days_since_pm"] = _days_since(idx, pm.get_group(mid) if mid in pm.groups else None)
        pf["days_since_cm"] = _days_since(idx, cm.get_group(mid) if mid in cm.groups else None)
        panels.append(pf.reset_index().rename(columns={"index": "date"}))

    panel = pd.concat(panels, ignore_index=True)
    # attach static attributes + age
    m = frames["machines"][["machine_id", "modality", "model", "country", "region",
                            "install_date", "scans_per_day"]].copy()
    m["install_date"] = pd.to_datetime(m["install_date"])
    panel = panel.merge(m.drop(columns=["modality"]), on="machine_id", how="left")
    panel["age_years"] = (panel["date"] - panel["install_date"]).dt.days / 365.25
    return panel


def _days_since(idx: pd.DatetimeIndex, events: pd.Series | None) -> np.ndarray:
    if events is None or len(events) == 0:
        return np.full(len(idx), 3650.0)
    ev = np.sort(pd.to_datetime(events).values)
    pos = np.searchsorted(ev, idx.values, side="right") - 1
    out = np.full(len(idx), 3650.0)
    ok = pos >= 0
    out[ok] = (idx.values[ok] - ev[pos[ok]]) / np.timedelta64(1, "D")
    return out


# --------------------------------------------------------------------------- #
# As-of slice + labels
# --------------------------------------------------------------------------- #
def feature_columns(panel: pd.DataFrame) -> list[str]:
    drop = {"machine_id", "date", "install_date", "model", "country", "region", "modality"}
    return [c for c in panel.columns if c not in drop and panel[c].dtype != object]


def features_asof(panel: pd.DataFrame, as_of, machine_ids=None) -> pd.DataFrame:
    """Latest feature row per machine at or before `as_of`."""
    as_of = pd.Timestamp(as_of)
    sub = panel[panel["date"] <= as_of]
    if machine_ids is not None:
        sub = sub[sub["machine_id"].isin(machine_ids)]
    latest = sub.sort_values("date").groupby("machine_id").tail(1).copy()
    latest["as_of_date"] = as_of
    return latest


def label_within(failures: pd.DataFrame, as_of, horizon_days: int, machine_ids) -> pd.Series:
    """1 if the machine has a failure in (as_of, as_of + horizon]."""
    as_of = pd.Timestamp(as_of)
    hi = as_of + pd.Timedelta(days=horizon_days)
    win = failures[(failures.failure_date > as_of) & (failures.failure_date <= hi)]
    hit = set(win["machine_id"].unique())
    return pd.Series({m: int(m in hit) for m in machine_ids})
