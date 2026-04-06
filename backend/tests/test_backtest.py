"""Unit tests for the backtest math.

No Neo4j, no yfinance, no DB — everything runs on synthetic pandas
Series fixtures so CI is deterministic and offline.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from evaluation.backtest import (
    BacktestResult,
    _actual_direction,
    _compute_alpha,
    _next_trading_day,
)


def _business_days_series(start: date, n: int, values: list[float]) -> pd.Series:
    """Build a pd.Series indexed by business days starting on `start`."""
    idx = pd.bdate_range(start=pd.Timestamp(start), periods=n)
    assert len(values) == n
    return pd.Series(values, index=idx)


def test_next_trading_day_weekend_rolls_forward():
    idx = pd.bdate_range(start="2024-01-01", periods=10)  # Mon Jan 1 start
    # Sunday 2024-01-07 → next trading day is Monday 2024-01-08
    ts = _next_trading_day(idx, date(2024, 1, 7))
    assert ts == pd.Timestamp("2024-01-08")


def test_next_trading_day_returns_none_past_end():
    idx = pd.bdate_range(start="2024-01-01", periods=5)
    assert _next_trading_day(idx, date(2030, 1, 1)) is None


def test_alpha_positive_when_sector_beats_benchmark():
    # Sector doubles over 30 business days, benchmark flat
    sector = _business_days_series(date(2024, 1, 1), 40, [100 + i for i in range(40)])
    bench = _business_days_series(date(2024, 1, 1), 40, [100.0] * 40)
    result = _compute_alpha(sector, bench, date(2024, 1, 1), lag=10)
    assert result is not None
    sector_ret, bench_ret, alpha = result
    assert sector_ret > 0
    assert bench_ret == 0
    assert alpha > 0


def test_alpha_negative_and_direction_reverses():
    # Sector falls 20%, benchmark up 5%
    sector = _business_days_series(date(2024, 1, 1), 30, [100 - i * 0.5 for i in range(30)])
    bench = _business_days_series(date(2024, 1, 1), 30, [100 + i * 0.1 for i in range(30)])
    result = _compute_alpha(sector, bench, date(2024, 1, 1), lag=15)
    assert result is not None
    _, _, alpha = result
    assert alpha < 0
    assert _actual_direction(alpha) == "negative"


def test_actual_direction_mapping():
    assert _actual_direction(0.01) == "positive"
    assert _actual_direction(-0.01) == "negative"
    assert _actual_direction(0.0) == "neutral"


def test_lag_window_returns_none_when_event_past_data_end():
    sector = _business_days_series(date(2024, 1, 1), 10, [100.0] * 10)
    bench = _business_days_series(date(2024, 1, 1), 10, [100.0] * 10)
    # Event date is after the last row
    assert _compute_alpha(sector, bench, date(2024, 6, 1), lag=5) is None


def test_event_on_saturday_uses_next_monday_not_friday():
    """Pure no-lookahead check. If the event lands on a weekend, the
    measurement window must start on the following trading day, NOT on
    the prior Friday's close."""
    # 2024-01-06 is a Saturday. 2024-01-05 is Fri, 2024-01-08 is Mon.
    idx = pd.bdate_range(start="2024-01-01", periods=15)
    sector = pd.Series(
        [100.0 if d < pd.Timestamp("2024-01-08") else 90.0 for d in idx],
        index=idx,
    )
    bench = pd.Series([100.0] * 15, index=idx)
    # If we (wrongly) used Friday's close we'd see sector_return = -10%.
    # Correct behavior: start from Monday, end at Monday+lag, both at 90.
    result = _compute_alpha(sector, bench, date(2024, 1, 6), lag=5)
    assert result is not None
    sector_ret, _, _ = result
    assert sector_ret == pytest.approx(0.0, abs=1e-9)


def test_backtest_result_is_frozen_dataclass():
    r = BacktestResult(
        event_date=date(2024, 1, 1),
        event_name="X",
        signal_type="commodity",
        sector="IT",
        predicted_direction="positive",
        actual_direction="positive",
        hit=True,
        sector_return=0.05,
        benchmark_return=0.02,
        sector_alpha=0.03,
        lag_days=20,
    )
    with pytest.raises(Exception):
        r.hit = False  # type: ignore[misc]
