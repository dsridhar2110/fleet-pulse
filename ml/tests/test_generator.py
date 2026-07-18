"""Sanity gates for the synthetic fleet: if these fail, the data is not defensible."""

from pathlib import Path

import pandas as pd
import pytest

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

pytestmark = pytest.mark.skipif(not RAW.exists(), reason="run `make data` first")


@pytest.fixture(scope="module")
def failures() -> pd.DataFrame:
    return pd.read_parquet(RAW / "failures.parquet")


@pytest.fixture(scope="module")
def fleet() -> pd.DataFrame:
    return pd.read_parquet(RAW / "fleet_master.parquet")


def test_failure_rate_in_band(failures, fleet):
    """Machine-week positive rate must land in the disclosed 1-3% band."""
    machine_weeks = len(fleet) * 365 / 7
    rate = len(failures) / machine_weeks
    assert 0.01 <= rate <= 0.03, f"machine-week failure rate {rate:.2%} outside 1-3%"


def test_sudden_failure_share(failures):
    """~15% of failures must have no precursor (config: sudden_failure_fraction)."""
    assert 0.08 <= failures["sudden"].mean() <= 0.25


def test_age_predicts_failure(failures, fleet):
    """Wear-out check: older machines must fail more often (Weibull k > 1 at work).

    If this fails, the hazard engine is broken and 'machine age' would be noise —
    the model would have no physics to learn.
    """
    df = fleet.merge(
        failures.groupby("machine_id").size().rename("n_failures"),
        left_on="machine_id",
        right_index=True,
        how="left",
    ).fillna({"n_failures": 0})
    df["age_years"] = (pd.Timestamp("2025-01-01") - df["install_date"]).dt.days / 365.25
    old = df[df.age_years >= df.age_years.median()]["n_failures"].mean()
    young = df[df.age_years < df.age_years.median()]["n_failures"].mean()
    assert old > young * 1.3, f"older half {old:.2f} vs younger half {young:.2f} failures/machine"


def test_benign_errors_dominate():
    """Most error volume must be uncorrelated noise — burst features are earned."""
    err = pd.read_parquet(RAW / "error_events.parquet")
    assert (err["severity"] == "info").mean() > 0.80


def test_no_telemetry_during_downtime(failures):
    """Machines report nothing while down."""
    tel = pd.read_parquet(RAW / "telemetry")
    f = failures.iloc[0]
    down = tel[
        (tel.machine_id == f.machine_id)
        & (tel.date > f.failure_date)
        & (tel.date < f.failure_date + pd.Timedelta(days=int(f.downtime_days)))
    ]
    assert down.empty
