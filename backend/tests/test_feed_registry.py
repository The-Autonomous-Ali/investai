"""Registry wiring tests — verify structure, not network calls."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def patch_redis_client():
    fake = MagicMock()
    fake.connect = AsyncMock()
    fake._redis = MagicMock()
    fake.xadd = AsyncMock(return_value=b"1-0")
    with patch("ingestion.base.get_client", return_value=fake):
        yield fake


def test_registry_imports_and_instantiates():
    from ingestion.feed_registry import get_all_connectors
    all_c = get_all_connectors()
    assert len(all_c) > 10
    # Every connector must have the four tagging fields populated.
    for c in all_c:
        assert c.name
        assert c.region in {"us", "eu", "uk", "jp", "cn", "in", "global"}
        assert c.tier in {1, 2, 3}
        assert c.category


def test_connector_names_are_unique():
    from ingestion.feed_registry import get_all_connectors
    names = [c.name for c in get_all_connectors()]
    assert len(names) == len(set(names)), "duplicate connector names"


def test_every_target_region_represented():
    """Sanity: at least one feed per core region."""
    from ingestion.feed_registry import get_connectors_by_region
    for region in ("us", "eu", "uk", "jp", "in", "global"):
        assert get_connectors_by_region(region), f"no connectors for region={region}"


def test_category_filter_works():
    from ingestion.feed_registry import get_connectors_by_category
    monetary = get_connectors_by_category("monetary")
    # Fed, ECB, BoE, BoJ, RBI at minimum
    assert len(monetary) >= 5
    names = {c.name for c in monetary}
    assert "fed-monetary" in names
    assert "ecb-press" in names
    assert "rbi-press" in names


def test_urls_are_http():
    """Every RSS URL must be http(s). Catches copy-paste typos."""
    from ingestion.connectors.rss import RSSConnector
    from ingestion.feed_registry import get_all_connectors
    for c in get_all_connectors():
        if isinstance(c, RSSConnector):
            assert c.url.startswith("http"), f"{c.name} url looks wrong: {c.url}"


def test_yfinance_groups_non_empty():
    from ingestion.connectors.yfinance_prices import YFinancePricesConnector
    from ingestion.feed_registry import get_all_connectors
    groups = [c for c in get_all_connectors() if isinstance(c, YFinancePricesConnector)]
    assert groups
    for g in groups:
        assert g.tickers, f"{g.name} has no tickers"


def test_fred_series_have_ids():
    from ingestion.connectors.fred import FredSeriesConnector
    from ingestion.feed_registry import get_all_connectors
    series = [c for c in get_all_connectors() if isinstance(c, FredSeriesConnector)]
    assert series
    ids = {c.series_id for c in series}
    # Core series present
    assert {"DFF", "DGS10", "CPIAUCSL"}.issubset(ids)
