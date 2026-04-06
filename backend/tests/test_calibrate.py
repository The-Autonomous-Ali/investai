"""Unit tests for the calibration aggregation and Wilson CI math."""
from datetime import date

import pytest

from evaluation.backtest import BacktestResult
from evaluation.calibrate import MIN_SAMPLE_SIZE, aggregate, wilson_ci


def _mk(event_name: str, sector: str, lag: int, hit: bool, alpha: float,
        pred_dir: str = "positive", signal_type: str = "commodity") -> BacktestResult:
    return BacktestResult(
        event_date=date(2024, 1, 1),
        event_name=event_name,
        signal_type=signal_type,
        sector=sector,
        predicted_direction=pred_dir,
        actual_direction="positive" if alpha > 0 else "negative" if alpha < 0 else "neutral",
        hit=hit,
        sector_return=alpha + 0.01,
        benchmark_return=0.01,
        sector_alpha=alpha,
        lag_days=lag,
    )


def test_wilson_ci_basic_properties():
    # Contains p
    lo, hi = wilson_ci(7, 10)
    assert lo <= 0.7 <= hi
    # Bounded
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_ci_tightens_with_more_samples():
    lo_small, hi_small = wilson_ci(7, 10)
    lo_big, hi_big = wilson_ci(700, 1000)
    # Same point estimate (0.7), but the bigger sample should give a
    # strictly narrower interval.
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_wilson_ci_handles_zero_samples():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_aggregate_groups_by_event_sector_lag():
    rows = [
        _mk("Oil Price Spike", "IT", 20, hit=True,  alpha=0.03),
        _mk("Oil Price Spike", "IT", 20, hit=False, alpha=-0.01),
        _mk("Oil Price Spike", "IT", 60, hit=True,  alpha=0.05),
        _mk("Oil Price Spike", "IT", 60, hit=True,  alpha=0.02),
        _mk("RBI Rate Hike",  "Banking", 20, hit=True,  alpha=0.04),
        _mk("RBI Rate Hike",  "Banking", 20, hit=True,  alpha=0.06),
    ]
    stats = aggregate(rows)
    assert len(stats) == 3
    key = {(s.event_name, s.sector, s.lag_days): s for s in stats}
    assert key[("Oil Price Spike", "IT", 20)].sample_size == 2
    assert key[("Oil Price Spike", "IT", 20)].hit_rate == 0.5
    assert key[("RBI Rate Hike", "Banking", 20)].hit_rate == 1.0


def test_sample_size_below_threshold_is_dropped():
    # Only one sample — should be filtered out.
    rows = [_mk("Oil Price Spike", "IT", 20, hit=True, alpha=0.03)]
    assert MIN_SAMPLE_SIZE == 2
    assert aggregate(rows) == []


def test_measured_strength_zero_when_sign_disagrees():
    # Predicted positive but actual alphas are negative on average →
    # measured_strength must clamp to 0.
    rows = [
        _mk("Oil Price Spike", "IT", 20, hit=False, alpha=-0.02, pred_dir="positive"),
        _mk("Oil Price Spike", "IT", 20, hit=False, alpha=-0.03, pred_dir="positive"),
    ]
    stats = aggregate(rows)
    assert len(stats) == 1
    assert stats[0].measured_strength == 0.0
    assert stats[0].avg_alpha < 0


def test_measured_strength_equals_hit_rate_when_sign_agrees():
    rows = [
        _mk("Oil Price Spike", "IT", 20, hit=True,  alpha=0.03, pred_dir="positive"),
        _mk("Oil Price Spike", "IT", 20, hit=True,  alpha=0.05, pred_dir="positive"),
        _mk("Oil Price Spike", "IT", 20, hit=False, alpha=0.02, pred_dir="positive"),
    ]
    stats = aggregate(rows)
    assert len(stats) == 1
    assert stats[0].hit_rate == pytest.approx(2/3)
    assert stats[0].measured_strength == pytest.approx(2/3)
    assert stats[0].avg_alpha > 0
