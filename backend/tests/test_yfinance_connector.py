"""Unit tests for YFinancePricesConnector — no real yfinance calls."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.connectors.yfinance_prices import YFinancePricesConnector


@pytest.fixture(autouse=True)
def patch_redis_client():
    fake = MagicMock()
    fake.connect = AsyncMock()
    fake._redis = MagicMock()
    fake._redis.sismember = AsyncMock(return_value=0)
    fake._redis.sadd = AsyncMock(return_value=1)
    fake._redis.expire = AsyncMock(return_value=True)
    fake.xadd = AsyncMock(return_value=b"1-0")
    with patch("ingestion.base.get_client", return_value=fake):
        yield fake


def _pd_frame_for(closes: list[float]):
    """Mock DataFrame-ish shape the connector expects."""
    import pandas as pd
    return pd.DataFrame({"Close": closes})


@pytest.fixture
def mock_yfinance_two_tickers():
    """Mock yfinance.download returning a multi-ticker frame."""
    import pandas as pd

    # Shape: columns = multi-index over (ticker, ohlc-field)
    arrays = [
        ["^GSPC", "^GSPC", "^VIX", "^VIX"],
        ["Close", "Open", "Close", "Open"],
    ]
    cols = pd.MultiIndex.from_arrays(arrays)
    data = [
        [4900.0, 4890.0, 14.0, 14.5],
        [4950.0, 4920.0, 13.0, 13.5],
    ]
    df = pd.DataFrame(data, columns=cols)

    mock_yf = MagicMock()
    mock_yf.download = MagicMock(return_value=df)

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        yield mock_yf


@pytest.mark.asyncio
async def test_yfinance_yields_signal_per_ticker(mock_yfinance_two_tickers):
    connector = YFinancePricesConnector(
        name="yf-us",
        tickers=["^GSPC", "^VIX"],
        region="us",
        tier=1,
        category="markets",
    )

    signals = [s async for s in connector.fetch()]

    assert len(signals) == 2

    gspc = next(s for s in signals if "GSPC" in s.source_name)
    payload = json.loads(gspc.raw_payload)
    assert payload["ticker"] == "^GSPC"
    assert payload["price"] == pytest.approx(4950.0)
    assert payload["prev_close"] == pytest.approx(4900.0)
    # +1.02% approx
    assert 1.0 < payload["change_pct"] < 1.05

    vix = next(s for s in signals if "VIX" in s.source_name)
    vix_payload = json.loads(vix.raw_payload)
    assert vix_payload["ticker"] == "^VIX"
    # VIX down from 14 to 13 = -7.14%
    assert vix_payload["change_pct"] == pytest.approx(-7.142857, rel=1e-3)


@pytest.mark.asyncio
async def test_yfinance_skips_ticker_with_insufficient_data():
    import pandas as pd

    arrays = [["A", "A", "B", "B"], ["Close", "Open", "Close", "Open"]]
    cols = pd.MultiIndex.from_arrays(arrays)
    # Only 1 close for A; 2 for B
    data = [
        [float("nan"), 100.0, 10.0, 11.0],
        [110.0, 105.0, 11.0, 12.0],
    ]
    df = pd.DataFrame(data, columns=cols)

    mock_yf = MagicMock()
    mock_yf.download = MagicMock(return_value=df)

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        connector = YFinancePricesConnector(
            name="yf-test",
            tickers=["A", "B"],
            region="us",
            tier=1,
            category="markets",
        )
        signals = [s async for s in connector.fetch()]

    tickers_seen = {json.loads(s.raw_payload)["ticker"] for s in signals}
    assert tickers_seen == {"B"}  # A skipped due to only 1 valid close


@pytest.mark.asyncio
async def test_yfinance_returns_empty_on_download_failure():
    mock_yf = MagicMock()
    mock_yf.download = MagicMock(side_effect=Exception("network down"))

    with patch.dict("sys.modules", {"yfinance": mock_yf}):
        connector = YFinancePricesConnector(
            name="yf-test",
            tickers=["^GSPC"],
            region="us",
            tier=1,
            category="markets",
        )
        signals = [s async for s in connector.fetch()]

    assert signals == []


@pytest.mark.asyncio
async def test_yfinance_title_includes_direction_arrow(mock_yfinance_two_tickers):
    connector = YFinancePricesConnector(
        name="yf-us",
        tickers=["^GSPC", "^VIX"],
        region="us",
        tier=1,
        category="markets",
    )
    signals = [s async for s in connector.fetch()]

    gspc = next(s for s in signals if "GSPC" in s.source_name)
    vix = next(s for s in signals if "VIX" in s.source_name)

    # GSPC went UP, so ↑ arrow; VIX went DOWN, so ↓ arrow
    assert "↑" in gspc.title
    assert "↓" in vix.title


@pytest.mark.asyncio
async def test_yfinance_url_includes_date_for_daily_dedup(mock_yfinance_two_tickers):
    connector = YFinancePricesConnector(
        name="yf-us",
        tickers=["^GSPC", "^VIX"],
        region="us",
        tier=1,
        category="markets",
    )
    signals = [s async for s in connector.fetch()]

    for s in signals:
        # yfinance://<ticker>/<YYYY-MM-DD>
        assert s.url.startswith("yfinance://")
        assert len(s.url.split("/")[-1]) == 10  # date portion
