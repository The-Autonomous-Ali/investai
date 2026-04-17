"""Unit tests for BaseConnector — dedup, emit, health tracking."""
from __future__ import annotations

import pytest
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

from ingestion.base import (
    BaseConnector,
    RawSignal,
    DEDUP_SET_KEY,
    DEDUP_TTL_SECONDS,
)


# ---- Test doubles --------------------------------------------------------

class _FakeRedisClient:
    """Shape-compatible with RedisStreamClient for BaseConnector's needs."""

    def __init__(self):
        self._redis = AsyncMock()
        self._redis.sismember = AsyncMock(return_value=0)
        self._redis.sadd = AsyncMock(return_value=1)
        self._redis.expire = AsyncMock(return_value=True)
        self.connect = AsyncMock()
        self.xadd_calls: list[dict] = []

    async def xadd(self, fields, *args, **kwargs):
        self.xadd_calls.append(fields)
        return b"1700000000-0"


class _FakeConnector(BaseConnector):
    name = "fake"
    region = "global"
    tier = 1
    category = "markets"

    def __init__(self, items: list[RawSignal] | None = None, raise_on: int | None = None):
        super().__init__()
        self._items = items or []
        self._raise_on = raise_on

    async def fetch(self) -> AsyncIterator[RawSignal]:
        for i, item in enumerate(self._items):
            if self._raise_on is not None and i == self._raise_on:
                raise RuntimeError("simulated fetch failure")
            yield item


def _make_signal(url: str, title: str = "t") -> RawSignal:
    return RawSignal(
        source_name="fake",
        source_region="global",
        source_tier=1,
        category="markets",
        url=url,
        title=title,
        body="body",
    )


# ---- RawSignal tests ----------------------------------------------------

def test_raw_signal_computes_content_hash():
    s = _make_signal("https://example.com/a")
    assert s.content_hash
    assert len(s.content_hash) == 64  # sha256 hex


def test_raw_signal_same_input_same_hash():
    a = _make_signal("https://example.com/a", title="t")
    b = _make_signal("https://example.com/a", title="t")
    assert a.content_hash == b.content_hash


def test_raw_signal_different_url_different_hash():
    a = _make_signal("https://example.com/a")
    b = _make_signal("https://example.com/b")
    assert a.content_hash != b.content_hash


def test_raw_signal_sets_fetched_at():
    s = _make_signal("https://example.com/a")
    assert s.fetched_at  # ISO timestamp set automatically


def test_raw_signal_stream_fields_all_strings():
    s = _make_signal("https://example.com/a")
    fields = s.to_stream_fields()
    assert all(isinstance(v, str) for v in fields.values())
    # None values should become empty string, not the literal "None"
    assert fields["published_at"] == ""


# ---- BaseConnector tests ------------------------------------------------

@pytest.fixture
def fake_redis():
    return _FakeRedisClient()


@pytest.fixture(autouse=True)
def patch_get_client(fake_redis):
    with patch("ingestion.base.get_client", return_value=fake_redis):
        yield fake_redis


@pytest.mark.asyncio
async def test_run_emits_new_signals(fake_redis):
    items = [_make_signal(f"https://a/{i}") for i in range(3)]
    connector = _FakeConnector(items=items)

    count = await connector.run()

    assert count == 3
    assert len(fake_redis.xadd_calls) == 3


@pytest.mark.asyncio
async def test_run_skips_duplicates_from_in_memory_cache(fake_redis):
    item = _make_signal("https://a/same")
    connector = _FakeConnector(items=[item, item, item])

    count = await connector.run()

    assert count == 1
    assert len(fake_redis.xadd_calls) == 1


@pytest.mark.asyncio
async def test_run_skips_duplicates_from_redis_set(fake_redis):
    # Simulate "already in Redis SET from a prior process"
    fake_redis._redis.sismember = AsyncMock(return_value=1)
    item = _make_signal("https://a/known")
    connector = _FakeConnector(items=[item])

    count = await connector.run()

    assert count == 0
    assert len(fake_redis.xadd_calls) == 0


@pytest.mark.asyncio
async def test_run_writes_hash_to_redis_set_with_ttl(fake_redis):
    item = _make_signal("https://a/new")
    connector = _FakeConnector(items=[item])

    await connector.run()

    fake_redis._redis.sadd.assert_awaited_with(DEDUP_SET_KEY, item.content_hash)
    fake_redis._redis.expire.assert_awaited_with(DEDUP_SET_KEY, DEDUP_TTL_SECONDS)


@pytest.mark.asyncio
async def test_run_survives_fetch_exception(fake_redis):
    items = [_make_signal("https://a/0"), _make_signal("https://a/1")]
    connector = _FakeConnector(items=items, raise_on=1)

    # Exception raised on second item — first should still be emitted
    count = await connector.run()

    assert count == 1
    assert connector.consecutive_failures == 1
    assert connector.last_run_at is not None
    # last_success_at stays None because the run failed
    assert connector.last_success_at is None


@pytest.mark.asyncio
async def test_run_resets_failure_counter_on_success(fake_redis):
    connector = _FakeConnector(items=[_make_signal("https://a/0")])
    connector.consecutive_failures = 5

    await connector.run()

    assert connector.consecutive_failures == 0


@pytest.mark.asyncio
async def test_health_unhealthy_after_three_failures(fake_redis):
    connector = _FakeConnector(items=[], raise_on=0)
    # _FakeConnector with raise_on=0 and empty items never raises because
    # the generator never starts. Use a version that does raise:
    connector = _FakeConnector(items=[_make_signal("u")], raise_on=0)

    await connector.run()
    await connector.run()
    status = connector.health_status()
    assert status["healthy"] is True  # 2 failures < 3

    await connector.run()
    status = connector.health_status()
    assert status["healthy"] is False  # 3 failures >= 3


@pytest.mark.asyncio
async def test_xadd_failure_does_not_record_hash_as_seen(fake_redis):
    """If xadd returns None (Redis down), we must not mark the hash as seen,
    so a retry on the next run can still emit it."""
    fake_redis.xadd = AsyncMock(return_value=None)
    item = _make_signal("https://a/retry-me")
    connector = _FakeConnector(items=[item])

    count = await connector.run()

    assert count == 0
    assert item.content_hash not in connector._hash_set


@pytest.mark.asyncio
async def test_redis_down_dedup_check_assumes_not_duplicate(fake_redis):
    """If SISMEMBER raises, the item should be emitted (Postgres is final gate)."""
    fake_redis._redis.sismember = AsyncMock(side_effect=Exception("redis down"))
    item = _make_signal("https://a/unsure")
    connector = _FakeConnector(items=[item])

    count = await connector.run()

    assert count == 1


def test_health_status_shape():
    connector = _FakeConnector()
    status = connector.health_status()
    assert set(status.keys()) == {
        "name",
        "region",
        "tier",
        "category",
        "last_run_at",
        "last_success_at",
        "consecutive_failures",
        "healthy",
    }
    assert status["name"] == "fake"
    assert status["healthy"] is True  # 0 failures
