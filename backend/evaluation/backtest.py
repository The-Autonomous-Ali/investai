"""Replay seeded historical events through the KG and measure actual
Indian sector alpha vs. the Nifty 50 benchmark.

The main entry point is `run_backtest`. It is deterministic and makes
no LLM calls — every number comes from yfinance closes already in
`sector_prices` and from KG traversal over Neo4j (or its fallback).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation.events_loader import HistoricalEvent
from evaluation.kg_query import KGPrediction, query_kg_for_event
from evaluation.price_loader import SECTOR_TO_TICKER, load_prices_from_db

logger = structlog.get_logger()

DEFAULT_LAG_WINDOWS: tuple[int, ...] = (5, 20, 60)
BENCHMARK_SYMBOL: str = "NIFTY_50"


@dataclass(frozen=True)
class BacktestResult:
    event_date: date
    event_name: str
    signal_type: str
    sector: str
    predicted_direction: str
    actual_direction: str
    hit: bool
    sector_return: float
    benchmark_return: float
    sector_alpha: float
    lag_days: int


def _next_trading_day(index: pd.DatetimeIndex, target: date) -> pd.Timestamp | None:
    """First index entry >= target. None if target is past the last row."""
    ts = pd.Timestamp(target)
    pos = index.searchsorted(ts, side="left")
    if pos >= len(index):
        return None
    return index[pos]


def _compute_alpha(
    sector_series: pd.Series,
    benchmark: pd.Series,
    event_date: date,
    lag: int,
) -> tuple[float, float, float] | None:
    """Return (sector_return, benchmark_return, alpha) for the measurement
    window, or None if either endpoint falls outside the data.

    Start is the first trading day on or after event_date — we never peek
    at event_date's close itself if event_date is intraday, because the
    price series stores only day closes and intraday news would otherwise
    leak into the start value. Using `searchsorted(side='left')` returns
    the event_date if a row exists for it (public after-hours news), or
    the next trading day if it was a weekend/holiday.
    """
    start = _next_trading_day(sector_series.index, event_date)
    if start is None:
        return None

    end_target = start.date() + timedelta(days=lag)
    end = _next_trading_day(sector_series.index, end_target)
    if end is None or end <= start:
        return None

    # Both series must cover both endpoints.
    if start not in benchmark.index or end not in benchmark.index:
        return None
    if start not in sector_series.index or end not in sector_series.index:
        return None

    s0 = float(sector_series.loc[start])
    s1 = float(sector_series.loc[end])
    b0 = float(benchmark.loc[start])
    b1 = float(benchmark.loc[end])
    if s0 == 0 or b0 == 0:
        return None

    sector_ret = s1 / s0 - 1.0
    bench_ret  = b1 / b0 - 1.0
    return sector_ret, bench_ret, sector_ret - bench_ret


def _actual_direction(alpha: float) -> str:
    if alpha > 0:
        return "positive"
    if alpha < 0:
        return "negative"
    return "neutral"


async def run_backtest(
    db: AsyncSession,
    neo4j_driver,
    events: Sequence[HistoricalEvent],
    lag_windows: Sequence[int] = DEFAULT_LAG_WINDOWS,
) -> list[BacktestResult]:
    """Replay every event in `events` through the KG and price data.

    For each event → each KG-predicted sector → each lag window, compute
    the sector's alpha vs. Nifty 50 benchmark and record whether the
    predicted direction matched the observed direction.
    """
    prices = await load_prices_from_db(db)
    if BENCHMARK_SYMBOL not in prices:
        logger.error("backtest.missing_benchmark", symbol=BENCHMARK_SYMBOL)
        return []
    benchmark = prices[BENCHMARK_SYMBOL]

    results: list[BacktestResult] = []
    events_with_predictions = 0

    for event in events:
        preds: list[KGPrediction] = await query_kg_for_event(
            neo4j_driver, event.event_name, event.signal_type
        )
        if not preds:
            continue
        events_with_predictions += 1

        for pred in preds:
            ticker_key = SECTOR_TO_TICKER.get(pred.sector)
            if not ticker_key or ticker_key not in prices:
                logger.debug(
                    "backtest.skip_sector",
                    event=event.event_name,
                    sector=pred.sector,
                    reason="no price series",
                )
                continue
            sector_series = prices[ticker_key]

            for lag in lag_windows:
                computed = _compute_alpha(sector_series, benchmark, event.date, lag)
                if computed is None:
                    continue
                sector_ret, bench_ret, alpha = computed
                actual = _actual_direction(alpha)
                results.append(BacktestResult(
                    event_date=event.date,
                    event_name=event.event_name,
                    signal_type=event.signal_type,
                    sector=pred.sector,
                    predicted_direction=pred.direction,
                    actual_direction=actual,
                    hit=(actual == pred.direction),
                    sector_return=sector_ret,
                    benchmark_return=bench_ret,
                    sector_alpha=alpha,
                    lag_days=lag,
                ))

    logger.info(
        "backtest.complete",
        events_total=len(events),
        events_with_predictions=events_with_predictions,
        result_rows=len(results),
    )
    return results
