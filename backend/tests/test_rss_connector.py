"""Unit tests for RSSConnector — no real network calls."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from ingestion.connectors.rss import RSSConnector, MAX_BODY_CHARS


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve Monetary Policy</title>
    <item>
      <title>Fed raises rates by 25bps</title>
      <link>https://www.federalreserve.gov/press/monetary/2026-04-17.htm</link>
      <description>The FOMC raised the federal funds rate target range...</description>
      <pubDate>Thu, 17 Apr 2026 18:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Powell press conference scheduled</title>
      <link>https://www.federalreserve.gov/press/monetary/2026-04-17b.htm</link>
      <description>Chair Powell will hold a press conference.</description>
      <pubDate>Thu, 17 Apr 2026 18:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


EMPTY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>"""


MALFORMED_ENTRY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title></title>
      <link>https://no-title/</link>
    </item>
    <item>
      <title>Valid entry</title>
      <link>https://valid/</link>
      <description>body</description>
    </item>
  </channel>
</rss>"""


def _make_http_client(text: str, status: int = 200):
    """Build a mock async httpx client returning a given body."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
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


@pytest.fixture(autouse=True)
def patch_get_client():
    """Every test gets a fresh mocked Redis client via BaseConnector."""
    fake_redis = MagicMock()
    fake_redis.connect = AsyncMock()
    fake_redis._redis = MagicMock()
    fake_redis._redis.sismember = AsyncMock(return_value=0)
    fake_redis._redis.sadd = AsyncMock(return_value=1)
    fake_redis._redis.expire = AsyncMock(return_value=True)
    fake_redis.xadd = AsyncMock(return_value=b"1-0")
    with patch("ingestion.base.get_client", return_value=fake_redis):
        yield fake_redis


@pytest.mark.asyncio
async def test_fetch_yields_rawsignal_per_entry():
    http = _make_http_client(SAMPLE_RSS)
    connector = RSSConnector(
        name="fed-monetary",
        url="https://example.com/feed.xml",
        region="us",
        tier=1,
        category="monetary",
        http_client=http,
    )

    signals = [s async for s in connector.fetch()]

    assert len(signals) == 2
    assert signals[0].title == "Fed raises rates by 25bps"
    assert signals[0].source_name == "fed-monetary"
    assert signals[0].source_region == "us"
    assert signals[0].source_tier == 1
    assert signals[0].category == "monetary"
    assert signals[0].url.startswith("https://www.federalreserve.gov/")
    assert signals[0].published_at is not None


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_empty_feed():
    http = _make_http_client(EMPTY_RSS)
    connector = RSSConnector(
        name="x", url="https://x", region="us", tier=1, category="monetary",
        http_client=http,
    )
    signals = [s async for s in connector.fetch()]
    assert signals == []


@pytest.mark.asyncio
async def test_fetch_skips_entries_without_title():
    http = _make_http_client(MALFORMED_ENTRY_RSS)
    connector = RSSConnector(
        name="x", url="https://x", region="us", tier=1, category="monetary",
        http_client=http,
    )
    signals = [s async for s in connector.fetch()]
    assert len(signals) == 1
    assert signals[0].title == "Valid entry"


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_http_error():
    http = _make_http_client("", status=500)
    connector = RSSConnector(
        name="x", url="https://x", region="us", tier=1, category="monetary",
        http_client=http,
    )
    signals = [s async for s in connector.fetch()]
    assert signals == []


@pytest.mark.asyncio
async def test_body_is_truncated_to_max_chars():
    big_desc = "X" * (MAX_BODY_CHARS + 500)
    rss = f"""<?xml version="1.0"?><rss><channel>
        <item><title>t</title><link>u</link><description>{big_desc}</description></item>
    </channel></rss>"""
    http = _make_http_client(rss)
    connector = RSSConnector(
        name="x", url="https://x", region="us", tier=1, category="monetary",
        http_client=http,
    )
    signals = [s async for s in connector.fetch()]
    assert len(signals[0].body) <= MAX_BODY_CHARS


@pytest.mark.asyncio
async def test_run_emits_two_signals_end_to_end(patch_get_client):
    http = _make_http_client(SAMPLE_RSS)
    connector = RSSConnector(
        name="fed-monetary",
        url="https://example.com/feed.xml",
        region="us",
        tier=1,
        category="monetary",
        http_client=http,
    )

    count = await connector.run()

    assert count == 2
    assert patch_get_client.xadd.await_count == 2
    assert connector.last_success_at is not None
    assert connector.consecutive_failures == 0
