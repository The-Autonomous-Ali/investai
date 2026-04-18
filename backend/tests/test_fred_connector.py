"""Unit tests for FredSeriesConnector — no real network calls."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingestion.connectors.fred import FredSeriesConnector


def _make_http_client(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=payload)
    if status >= 400:
        resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "err", request=MagicMock(), response=resp
        ))
    else:
        resp.raise_for_status = MagicMock(return_value=None)

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.aclose = AsyncMock()
    return client


def _make_failing_http_client(exc: Exception):
    client = MagicMock()
    client.get = AsyncMock(side_effect=exc)
    client.aclose = AsyncMock()
    return client


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


def _connector(http):
    return FredSeriesConnector(
        name="fred-fed-funds",
        series_id="DFF",
        human_label="US Fed Funds Rate",
        region="us",
        tier=1,
        category="monetary",
        http_client=http,
    )


@pytest.mark.asyncio
async def test_fetch_yields_signal_with_change_pct():
    payload = {
        "observations": [
            {"date": "2026-04-17", "value": "4.33"},
            {"date": "2026-04-16", "value": "4.58"},
        ]
    }
    http = _make_http_client(payload)
    with patch.dict("os.environ", {"FRED_API_KEY": "fake"}):
        signals = [s async for s in _connector(http).fetch()]

    assert len(signals) == 1
    s = signals[0]
    body = json.loads(s.raw_payload)
    assert body["series_id"] == "DFF"
    assert body["latest_value"] == pytest.approx(4.33)
    assert body["prior_value"] == pytest.approx(4.58)
    # (4.33 - 4.58) / 4.58 * 100 ≈ -5.459
    assert body["change_pct"] == pytest.approx(-5.459, rel=1e-2)
    assert "↓" in s.title
    assert s.url.endswith("#obs-2026-04-17")
    assert s.source_region == "us"
    assert s.category == "monetary"


@pytest.mark.asyncio
async def test_fetch_returns_empty_when_api_key_missing():
    http = _make_http_client({"observations": []})
    # Ensure env var is absent
    with patch.dict("os.environ", {}, clear=True):
        signals = [s async for s in _connector(http).fetch()]

    assert signals == []
    http.get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_skips_missing_value_marker():
    # FRED uses "." for missing values on the latest observation.
    payload = {
        "observations": [
            {"date": "2026-04-17", "value": "."},
            {"date": "2026-04-16", "value": "4.58"},
        ]
    }
    http = _make_http_client(payload)
    with patch.dict("os.environ", {"FRED_API_KEY": "fake"}):
        signals = [s async for s in _connector(http).fetch()]

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_network_failure():
    http = _make_failing_http_client(httpx.ConnectError("boom"))
    with patch.dict("os.environ", {"FRED_API_KEY": "fake"}):
        signals = [s async for s in _connector(http).fetch()]

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_handles_single_observation_no_prior():
    payload = {"observations": [{"date": "2026-04-17", "value": "4.33"}]}
    http = _make_http_client(payload)
    with patch.dict("os.environ", {"FRED_API_KEY": "fake"}):
        signals = [s async for s in _connector(http).fetch()]

    assert len(signals) == 1
    body = json.loads(signals[0].raw_payload)
    assert body["latest_value"] == pytest.approx(4.33)
    assert body["prior_value"] is None
    assert body["change_pct"] is None


@pytest.mark.asyncio
async def test_url_includes_observation_date_for_uniqueness():
    payload = {
        "observations": [
            {"date": "2026-04-17", "value": "4.33"},
            {"date": "2026-04-16", "value": "4.58"},
        ]
    }
    http = _make_http_client(payload)
    with patch.dict("os.environ", {"FRED_API_KEY": "fake"}):
        signals = [s async for s in _connector(http).fetch()]

    assert "#obs-2026-04-17" in signals[0].url


@pytest.mark.asyncio
async def test_published_at_is_iso_date():
    payload = {
        "observations": [
            {"date": "2026-04-17", "value": "4.33"},
            {"date": "2026-04-16", "value": "4.58"},
        ]
    }
    http = _make_http_client(payload)
    with patch.dict("os.environ", {"FRED_API_KEY": "fake"}):
        signals = [s async for s in _connector(http).fetch()]

    assert signals[0].published_at is not None
    assert signals[0].published_at.startswith("2026-04-17")
