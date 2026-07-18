# %% [markdown]
# # Fleet Pulse — Basic EDA on the raw datasets
#
# Run this file cell-by-cell (each `# %%` is one cell, like a Jupyter notebook).
# In Cursor/VS Code: click "Run Cell" above any `# %%`, or Shift+Enter inside a cell.
#
# What it covers, for every raw table:
#   1. shape            — how many rows / columns
#   2. dtypes           — data type of every column
#   3. head             — first rows, so you can picture the data
#   4. missing values   — which columns have NaNs and how many
#   5. key breakdowns   — value_counts on the important categorical columns
#   6. class balance    — the failure rate the model actually has to learn
#
# Data dictionary (what each table stands for):
#   fleet_master  — 1 row per machine: the asset register (dimension table)
#   telemetry     — 1 row per machine-day-sensor: daily sensor readings (long format)
#   error_events  — 1 row per error-code emission
#   failures      — 1 row per failure: the GROUND TRUTH the label is built from
#   maintenance   — 1 row per maintenance visit (scheduled/corrective)
#   tickets       — 1 row per service ticket, with free-text engineer notes

# %% Setup — imports and display options
from pathlib import Path

import pandas as pd

pd.set_option("display.max_columns", 50)      # never hide columns
pd.set_option("display.width", 250)           # don't wrap wide tables
pd.set_option("display.max_colwidth", 90)     # show ticket note text

# Locate ml/data/raw by walking up from wherever we're running
# (works both as a script and inside a notebook kernel, where __file__ doesn't exist)
_start = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
for _dir in [_start, *_start.parents]:
    if (_dir / "data" / "raw").exists():
        DATA = _dir / "data" / "raw"
        break
else:
    raise FileNotFoundError("Couldn't find ml/data/raw — open/run this from inside the fleet-pulse repo")
print("Reading from:", DATA)

# %% Load all six tables (telemetry is a partitioned FOLDER of parquet files)
fleet = pd.read_parquet(DATA / "fleet_master.parquet")
telemetry = pd.read_parquet(DATA / "telemetry")
errors = pd.read_parquet(DATA / "error_events.parquet")
failures = pd.read_parquet(DATA / "failures.parquet")
maintenance = pd.read_parquet(DATA / "maintenance.parquet")
tickets = pd.read_parquet(DATA / "tickets.parquet")

tables = {
    "fleet_master": fleet,
    "telemetry": telemetry,
    "error_events": errors,
    "failures": failures,
    "maintenance": maintenance,
    "tickets": tickets,
}
for name, df in tables.items():
    print(f"{name:<14} {df.shape[0]:>9,} rows x {df.shape[1]:>2} cols")

# %% Shapes + dtypes overview of ALL tables in one place
for name, df in tables.items():
    print(f"\n=== {name} — {df.shape[0]:,} rows x {df.shape[1]} cols ===")
    print(df.dtypes.to_string())

# %% Missing values overview — which columns have NaNs, and how many
for name, df in tables.items():
    na = df.isna().sum()
    na = na[na > 0]
    if na.empty:
        print(f"{name:<14} no missing values")
    else:
        print(f"\n{name}:")
        for col, n in na.items():
            print(f"  {col:<16} {n:>6,} missing ({n / len(df):.1%})")
# Note: NaN in maintenance.component / tickets.part_replaced is MEANINGFUL —
# preventive visits aren't tied to a component and replace no part.

# %% ---------------------------------------------------------------
# 1) FLEET_MASTER — the asset register (1 row per machine)
# %% fleet_master: head
fleet.head()

# %% fleet_master: what the fleet is made of
print("Modality mix:")
print(fleet["modality"].value_counts(), "\n")
print("By region:")
print(fleet["region"].value_counts(), "\n")
print("By country:")
print(fleet["country"].value_counts(), "\n")
print("Machine models:")
print(fleet["model"].value_counts(), "\n")
print("Flaky reporters (worse data quality):", fleet["flaky_reporter"].sum(), "machines")

# %% fleet_master: numeric + date ranges
print(fleet["scans_per_day"].describe(), "\n")
print("Install dates:", fleet["install_date"].min().date(), "→", fleet["install_date"].max().date())
print("Fleet age (years):")
print(((pd.Timestamp("2025-12-31") - fleet["install_date"]).dt.days / 365.25).describe())

# %% ---------------------------------------------------------------
# 2) TELEMETRY — daily sensor readings, LONG format (machine, day, sensor, value)
# %% telemetry: head
telemetry.head()

# %% telemetry: which sensors exist, per modality
# Long format means each machine emits SEVERAL rows per day — one per sensor.
print("Sensors per modality:")
print(telemetry.groupby("modality", observed=True)["sensor"].unique().to_string(), "\n")
print("Rows per sensor:")
print(telemetry["sensor"].value_counts())

# %% telemetry: coverage and missingness
print("Date range:", telemetry["date"].min().date(), "→", telemetry["date"].max().date())
print("Machines reporting:", telemetry["machine_id"].nunique())

# expected days vs actual days per machine → the deliberate ~3% missing-day gap
days_per_machine = telemetry.groupby("machine_id")["date"].nunique()
total_days = (telemetry["date"].max() - telemetry["date"].min()).days + 1
print(f"\nExpected days per machine: {total_days}")
print("Actual days per machine:")
print(days_per_machine.describe())

# %% telemetry: value distributions per sensor (spot the scales)
telemetry.groupby("sensor")["value"].describe().round(2)

# %% telemetry: one machine, one sensor — the time-series shape the model sees
one = telemetry[(telemetry["machine_id"] == "FP-MRI-0001") & (telemetry["sensor"] == "helium_level")]
one = one.sort_values("date")
print(one.head(10).to_string())
print("...")
print(one.tail(5).to_string())
# Try plotting it: one.plot(x="date", y="value", title="FP-MRI-0001 helium level")

# %% ---------------------------------------------------------------
# 3) ERROR_EVENTS — error-code emissions (mostly benign noise, by design)
# %% error_events: head
errors.head()

# %% error_events: severity & family breakdown
print("Severity (note: overwhelmingly 'info' — bursts must EARN their signal):")
print(errors["severity"].value_counts(), "\n")
print("Error families:")
print(errors["family"].value_counts(), "\n")
print("Top error codes:")
print(errors["error_code"].value_counts().head(15))

# %% error_events: volume per machine (are some machines noisier?)
per_machine = errors.groupby("machine_id").size()
print("Error events per machine:")
print(per_machine.describe())

# %% ---------------------------------------------------------------
# 4) FAILURES — the ground truth (this is what we predict)
# %% failures: head
failures.head()

# %% failures: what breaks, and how often
print("Failures by component:")
print(failures["component"].value_counts(), "\n")
print("Sudden failures (no precursor — unpredictable by design):")
print(failures["sudden"].value_counts(normalize=True).round(3), "\n")
print("Downtime days:")
print(failures["downtime_days"].describe())

# %% failures: CLASS BALANCE — the number that shapes the whole ML problem
n_machines = fleet.shape[0]
n_weeks = 52
machine_weeks = n_machines * n_weeks
print(f"Failures in the year:        {len(failures):,}")
print(f"Machine-weeks in the year:   {machine_weeks:,}  ({n_machines} machines x {n_weeks} weeks)")
print(f"Failure rate per machine-week: {len(failures) / machine_weeks:.2%}")
print("→ ~1-2% positives = heavy class imbalance; accuracy is useless,")
print("  which is why the model reports PR-AUC / precision@k instead.")

# %% failures: which machines fail most
print(failures["machine_id"].value_counts().head(10))
print(f"\nMachines with ≥1 failure: {failures['machine_id'].nunique()} of {n_machines}")

# %% ---------------------------------------------------------------
# 5) MAINTENANCE — scheduled (preventive) vs corrective visits
# %% maintenance: head
maintenance.head()

# %% maintenance: type breakdown
print(maintenance["maintenance_type"].value_counts(), "\n")
print("Corrective visits by component (should mirror failures):")
print(maintenance["component"].value_counts())

# %% ---------------------------------------------------------------
# 6) TICKETS — service tickets with FREE-TEXT engineer notes (the NLP material)
# %% tickets: head
tickets.head()

# %% tickets: type / parts / engineers
print(tickets["ticket_type"].value_counts(), "\n")
print("Parts replaced (corrective only):")
print(tickets["part_replaced"].value_counts(), "\n")
print("Engineers:", tickets["engineer_id"].nunique(), "unique IDs")

# %% tickets: read some real note text — inconsistent shorthand is DELIBERATE
# ("He level low" vs "helium lvl dropping" vs "cryo issue" — motivates NLP/retrieval)
for note in tickets.loc[tickets["ticket_type"] == "corrective", "note_text"].head(12):
    print("•", note)

# %% ---------------------------------------------------------------
# 7) CROSS-TABLE SANITY — one machine's full story, all tables joined by machine_id
MACHINE = "FP-MRI-0001"
print(f"=== {MACHINE} ===\n")
print(fleet[fleet["machine_id"] == MACHINE].to_string(index=False), "\n")
print("Failures:")
print(failures[failures["machine_id"] == MACHINE].to_string(index=False), "\n")
print("Maintenance:")
print(maintenance[maintenance["machine_id"] == MACHINE].to_string(index=False), "\n")
print("Tickets:")
print(tickets[tickets["machine_id"] == MACHINE][["open_date", "close_date", "ticket_type", "component", "note_text"]].to_string(index=False))
# Notice the story lines up: failure on 2025-07-18 → corrective maintenance →
# ticket with matching dates and a note describing the fix.
