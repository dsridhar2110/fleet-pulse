"""PySpark feature engineering over the raw parquet lake.

Produces one row per (machine_id, scoring_date) — weekly Mondays — with all
features computed from data at or before the scoring date ONLY (rolling
windows via rangeBetween ending at the current day). The label is attached
separately in labels.py, from the FUTURE window (t, t+7] — the two never
touch the same data, and tests/test_no_leakage.py asserts it stays that way.

This job runs unmodified on a Databricks cluster: the only local-mode
specifics are the master URL and file paths.
"""

from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.sql.window import Window

ROOT = Path(__file__).resolve().parents[2]
RAW = str(ROOT / "data" / "raw")
OUT = str(ROOT / "data" / "features")

SENSOR_WINDOWS = [7, 14, 30]  # days
ERROR_WINDOWS = [7, 30]


def rolling_sensor_features(tel: DataFrame) -> DataFrame:
    """Per (machine, sensor, day): rolling mean/std/min/max + slope.

    Slope over the window via the covariance trick:
        slope = covar_samp(day_index, value) / var_samp(day_index)
    which is the OLS slope of value on time — cheap drift detection.
    """
    tel = tel.withColumn("day_idx", F.datediff("date", F.lit("2025-01-01")))

    out = tel.select("machine_id", "sensor", "date", "day_idx", "value")
    for w in SENSOR_WINDOWS:
        win = (
            Window.partitionBy("machine_id", "sensor")
            .orderBy("day_idx")
            .rangeBetween(-(w - 1), 0)  # window END is the current day: no future data
        )
        out = (
            out.withColumn(f"mean_{w}d", F.mean("value").over(win))
            .withColumn(f"std_{w}d", F.stddev("value").over(win))
            .withColumn(f"min_{w}d", F.min("value").over(win))
            .withColumn(f"max_{w}d", F.max("value").over(win))
            .withColumn(
                f"slope_{w}d",
                F.covar_samp("day_idx", "value").over(win)
                / F.nullif(F.var_samp("day_idx").over(win), F.lit(0.0)),
            )
        )
    return out


def pivot_to_wide(daily: DataFrame, scoring: DataFrame) -> DataFrame:
    """Keep only scoring dates, then pivot sensors into named feature columns."""
    stats = [f"{s}_{w}d" for w in SENSOR_WINDOWS for s in ("mean", "std", "min", "max", "slope")]
    joined = daily.join(scoring, on=["machine_id", "date"], how="inner")
    exprs = [F.first(F.col(st)).alias(st) for st in stats]
    wide = joined.groupBy("machine_id", "date").pivot("sensor").agg(*exprs)
    return wide


def error_features(err: DataFrame, scoring: DataFrame) -> DataFrame:
    """Rolling error counts by severity + warning-family burst ratio."""
    daily = (
        err.groupBy("machine_id", "date")
        .agg(
            F.count("*").alias("err_total"),
            F.sum((F.col("severity") == "warning").cast("int")).alias("err_warn"),
            F.sum((F.col("severity") == "critical").cast("int")).alias("err_crit"),
        )
        .withColumn("day_idx", F.datediff("date", F.lit("2025-01-01")))
    )
    out = daily
    for w in ERROR_WINDOWS:
        win = Window.partitionBy("machine_id").orderBy("day_idx").rangeBetween(-(w - 1), 0)
        out = (
            out.withColumn(f"err_total_{w}d", F.sum("err_total").over(win))
            .withColumn(f"err_warn_{w}d", F.sum("err_warn").over(win))
            .withColumn(f"err_crit_{w}d", F.sum("err_crit").over(win))
        )
    # Burst ratio: last 7d of warnings vs the machine's trailing 90d daily average.
    win90 = Window.partitionBy("machine_id").orderBy("day_idx").rangeBetween(-89, 0)
    out = out.withColumn(
        "warn_burst_ratio",
        F.col("err_warn_7d") / F.nullif(F.sum("err_warn").over(win90) / 90.0 * 7.0, F.lit(0.0)),
    )
    cols = ["machine_id", "date", "warn_burst_ratio"] + [
        f"err_{k}_{w}d" for w in ERROR_WINDOWS for k in ("total", "warn", "crit")
    ]
    return out.select(*cols).join(scoring, on=["machine_id", "date"], how="inner")


def maintenance_features(maint: DataFrame, scoring: DataFrame) -> DataFrame:
    """Days since last scheduled / corrective maintenance, as of each scoring date."""
    m = maint.select("machine_id", F.col("date").alias("mdate"), "maintenance_type")
    s = scoring.select("machine_id", "date")
    joined = s.join(m, on="machine_id", how="left").where(F.col("mdate") <= F.col("date"))
    agg = joined.groupBy("machine_id", "date").agg(
        F.max(F.when(F.col("maintenance_type") == "scheduled", F.col("mdate"))).alias("last_pm"),
        F.max(F.when(F.col("maintenance_type") == "corrective", F.col("mdate"))).alias("last_cm"),
    )
    return s.join(agg, on=["machine_id", "date"], how="left").select(
        "machine_id",
        "date",
        F.coalesce(F.datediff("date", "last_pm"), F.lit(9999)).alias("days_since_pm"),
        F.coalesce(F.datediff("date", "last_cm"), F.lit(9999)).alias("days_since_cm"),
    )


def main() -> None:
    spark = (
        SparkSession.builder.master("local[*]")
        .appName("fleet-pulse-features")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    tel = spark.read.parquet(f"{RAW}/telemetry")
    err = spark.read.parquet(f"{RAW}/error_events.parquet")
    maint = spark.read.parquet(f"{RAW}/maintenance.parquet")
    fleet = spark.read.parquet(f"{RAW}/fleet_master.parquet")

    # Weekly scoring dates = Mondays on which the machine actually reported
    # (a machine that is down or offline that day is not scoreable in production).
    scoring = (
        tel.where(F.dayofweek("date") == 2)  # Monday
        .select("machine_id", "date")
        .distinct()
    )

    wide = pivot_to_wide(rolling_sensor_features(tel), scoring)
    errf = error_features(err, scoring)
    maintf = maintenance_features(maint, scoring)

    static = fleet.select(
        "machine_id",
        "modality",
        "model",
        "country",
        "install_date",
        F.col("scans_per_day").alias("baseline_scans_per_day"),
    )

    features = (
        wide.join(errf, ["machine_id", "date"], "left")
        .join(maintf, ["machine_id", "date"], "left")
        .join(static, "machine_id", "left")
        .withColumn("age_years", F.datediff("date", "install_date") / F.lit(365.25))
        .drop("install_date")
        .fillna(0, subset=["warn_burst_ratio"])
    )

    features.write.mode("overwrite").parquet(f"{OUT}/feature_table.parquet")
    n = features.count()
    n_cols = len(features.columns)
    print(f"feature table: {n:,} rows x {n_cols} cols -> {OUT}/feature_table.parquet")
    spark.stop()


if __name__ == "__main__":
    main()
