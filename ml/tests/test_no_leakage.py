"""The tests that make the model trustworthy: no feature may use data after t.

Two independent checks:
1. RECOMPUTE check — for sampled (machine, scoring_date) rows, recompute a
   rolling feature directly from raw telemetry truncated at t and require an
   exact match with the feature table. If any future data leaked into the
   window, the values would differ.
2. LABEL GEOMETRY check — every positive label's failure lies STRICTLY after
   the scoring date and within the 7-day horizon; failures on the scoring
   date itself never produce a positive (the failure-day tautology trap).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data/features/labeled.parquet"

pytestmark = pytest.mark.skipif(not FEATURES.exists(), reason="run `make features` first")


@pytest.fixture(scope="module")
def labeled() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_rolling_features_use_only_past_data(labeled):
    tel = pd.read_parquet(ROOT / "data/raw/telemetry")
    tel["date"] = pd.to_datetime(tel["date"])

    rng = np.random.default_rng(0)
    # Bias the sample toward positives — where leakage would matter most.
    pos = labeled[labeled.label == 1]
    sample = pd.concat([pos.sample(min(20, len(pos)), random_state=0),
                        labeled.sample(30, random_state=0)])

    checked = 0
    for _, row in sample.iterrows():
        m_tel = tel[(tel.machine_id == row.machine_id)]
        for sensor in m_tel.sensor.unique()[:2]:
            col = f"{sensor}_mean_30d"
            if col not in row.index or pd.isna(row[col]):
                continue
            window = m_tel[
                (m_tel.sensor == sensor)
                & (m_tel.date > row.date - pd.Timedelta(days=30))
                & (m_tel.date <= row.date)  # <= t: the window may touch t, never pass it
            ]["value"]
            assert np.isclose(window.mean(), row[col], rtol=1e-6), (
                f"{row.machine_id} {sensor} @ {row.date}: leakage or window bug"
            )
            checked += 1
    assert checked >= 20, "sample too small to be meaningful"


def test_positive_labels_are_strictly_future(labeled):
    pos = labeled[labeled.label == 1]
    assert len(pos) > 0
    dtf = pos["days_to_failure"]
    assert (dtf >= 1).all(), "a failure ON the scoring date leaked into the label"
    assert (dtf <= 7).all(), "label horizon exceeded"


def test_negative_labels_have_no_failure_in_horizon(labeled):
    neg = labeled[labeled.label == 0]
    in_horizon = neg["days_to_failure"].dropna()
    assert (in_horizon > 7).all()


def test_forbidden_columns_never_reach_the_model():
    """train_xgb.py must exclude evaluation-only and post-hoc columns."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from models.train_xgb import FORBIDDEN

    for col in ["days_to_failure", "next_failure_date", "component", "sudden", "label", "split"]:
        assert col in FORBIDDEN
