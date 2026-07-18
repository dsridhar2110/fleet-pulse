# %% [markdown]
# # FleetPulse on Databricks — PySpark feature engineering (the real thing)
#
# **What this notebook proves:** the exact feature pipeline that runs locally
# (`ml/src/pipeline/features_spark.py`) runs **unmodified in its logic** on a real
# Databricks workspace — the only changes are the file paths (a Unity Catalog
# Volume instead of a local folder) and that Databricks provides the `spark`
# session for us.
#
# **Before running — one-time setup (5 minutes, in the Databricks UI):**
# 1. Left sidebar → **Catalog** → catalog `workspace` → schema `default` →
#    **Create → Volume** → name it `fleetpulse`.
# 2. Open the new volume → **Upload to this volume** → drag in the 6 files from
#    `ml/data/databricks_upload/` on the Mac (telemetry.parquet, fleet_master.parquet,
#    error_events.parquet, failures.parquet, maintenance.parquet, tickets.parquet).
# 3. Workspace → **Import** → this notebook file → attach to **Serverless** compute → **Run all**.
#
# **Expected final result:** `feature table: 24,867 rows x 226 cols` — identical
# to the local run. Same code, same data, same answer, different engine. That's
# the point.

# %% Paths — the ONLY thing that changes vs the local pipeline
VOL = "/Volumes/workspace/default/fleetpulse"

RAW_TELEMETRY = f"{VOL}/telemetry.parquet"
RAW_ERRORS = f"{VOL}/error_events.parquet"
RAW_MAINT = f"{VOL}/maintenance.parquet"
RAW_FLEET = f"{VOL}/fleet_master.parquet"
OUT_FEATURES = f"{VOL}/feature_table"

# %% Read the raw tables (spark session is provided by Databricks)
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.window import Window

tel = spark.read.parquet(RAW_TELEMETRY)
err = spark.read.parquet(RAW_ERRORS)
maint = spark.read.parquet(RAW_MAINT)
fleet = spark.read.parquet(RAW_FLEET)

print(f"telemetry     {tel.count():>10,} rows")
print(f"error_events  {err.count():>10,} rows")
print(f"maintenance   {maint.count():>10,} rows")
print(f"fleet_master  {fleet.count():>10,} rows")
display(tel.limit(5))

# %% [markdown]
# ## The feature logic — identical to `features_spark.py`
#
# One row per (machine, Monday): rolling sensor statistics over 7/14/30-day
# windows **ending at the scoring day** (`rangeBetween(-(w-1), 0)` — the window
# never sees the future; that's the leakage guarantee), error-burst counts,
# and days-since-maintenance.

# %% Rolling sensor features: mean/std/min/max + OLS slope per window
SENSOR_WINDOWS = [7, 14, 30]
ERROR_WINDOWS = [7, 30]


def rolling_sensor_features(tel: DataFrame) -> DataFrame:
    tel = tel.withColumn("day_idx", F.datediff("date", F.lit("2025-01-01")))
    out = tel.select("machine_id", "sensor", "date", "day_idx", "value")
    for w in SENSOR_WINDOWS:
        win = (
            Window.partitionBy("machine_id", "sensor")
            .orderBy("day_idx")
            .rangeBetween(-(w - 1), 0)  # window ENDS at the current day: no future data
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
    stats = [f"{s}_{w}d" for w in SENSOR_WINDOWS for s in ("mean", "std", "min", "max", "slope")]
    joined = daily.join(scoring, on=["machine_id", "date"], how="inner")
    exprs = [F.first(F.col(st)).alias(st) for st in stats]
    return joined.groupBy("machine_id", "date").pivot("sensor").agg(*exprs)


def error_features(err: DataFrame, scoring: DataFrame) -> DataFrame:
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

print("feature functions defined — same code as ml/src/pipeline/features_spark.py")

# %% [markdown]
# ## Build the feature table
# Scoring dates = Mondays on which the machine actually reported (a machine that
# is offline that day is not scoreable in production either).

# %% Run the pipeline
scoring = (
    tel.where(F.dayofweek("date") == 2)  # Monday
    .select("machine_id", "date")
    .distinct()
)
print(f"scoring points (machine-Mondays): {scoring.count():,}")

wide = pivot_to_wide(rolling_sensor_features(tel), scoring)
errf = error_features(err, scoring)
maintf = maintenance_features(maint, scoring)

static = fleet.select(
    "machine_id", "modality", "model", "country", "install_date",
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

n, n_cols = features.count(), len(features.columns)
print(f"feature table: {n:,} rows x {n_cols} cols")
print("expected (local run): 24,867 rows x 226 cols — should match exactly")
display(features.limit(5))

# %% Write the feature table back to the volume (and register it as a table)
features.write.mode("overwrite").parquet(OUT_FEATURES)
features.write.mode("overwrite").saveAsTable("workspace.default.fleetpulse_features")
print("wrote:", OUT_FEATURES)
print("registered table: workspace.default.fleetpulse_features")

# %% [markdown]
# ## Prove it with SQL — the table is now queryable like a warehouse table

# %% A taste of the analytical layer (Spark SQL over the registered table)
display(spark.sql("""
    SELECT modality,
           COUNT(*)                        AS machine_weeks,
           ROUND(AVG(age_years), 1)        AS avg_age_years,
           ROUND(AVG(err_warn_7d), 2)      AS avg_warnings_last_7d
    FROM workspace.default.fleetpulse_features
    GROUP BY modality
    ORDER BY machine_weeks DESC
"""))

# %% [markdown]
# ## Done — what to screenshot for the evidence pack
# 1. The row/column count cell (`24,867 rows x 226 cols`) — same answer as local.
# 2. The Catalog page showing `workspace.default.fleetpulse_features`.
# 3. This notebook's header showing the Databricks workspace URL.
#
# **The interview line:** *"My feature job is plain PySpark — I developed it
# locally for fast iteration and ran the identical DataFrame code on Databricks
# serverless; the only difference was the storage path. That's the portability
# Spark buys you — locally it's my laptop, at Siemens it's Azure Databricks over
# Blob storage."*
