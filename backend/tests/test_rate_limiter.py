"""Unit tests for services.rate_limiter.

Uses a minimal in-memory fake of the small subset of Redis sorted-set
operations we rely on. Avoids the fakeredis dependency and matches the
existing AsyncMock-based test style in the repo.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services import rate_limiter


class FakePipeline:
    def __init__(self, client: "FakeRedis"):
        self.client = client
        self._ops = []

    def zremrangebyscore(self, key, mn, mx):
        self._ops.append(("zremrangebyscore", key, mn, mx))
        return self

    def zcard(self, key):
        self._ops.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self._ops.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))
        return self

    async def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "zremrangebyscore":
                _, key, mn, mx = op
                results.append(self.client._zremrangebyscore(key, mn, mx))
            elif op[0] == "zcard":
                _, key = op
                results.append(self.client._zcard(key))
            elif op[0] == "zadd":
                _, key, mapping = op
                results.append(self.client._zadd(key, mapping))
            elif op[0] == "expire":
                _, key, seconds = op
                results.append(self.client._expire(key, seconds))
        self._ops.clear()
        return results


class FakeRedis:
    """Tiny in-memory Redis stand-in for sliding-window tests."""

    def __init__(self):
        self.store: dict[str, list[tuple[str, float]]] = {}
        self.expires: dict[str, int] = {}

    def pipeline(self):
        return FakePipeline(self)

    def _zremrangebyscore(self, key, mn, mx):
        bucket = self.store.get(key, [])
        kept = [(m, s) for m, s in bucket if not (mn <= s <= mx)]
        removed = len(bucket) - len(kept)
        self.store[key] = kept
        return removed

    def _zcard(self, key):
        return len(self.store.get(key, []))

    def _zadd(self, key, mapping):
        bucket = self.store.setdefault(key, [])
        for member, score in mapping.items():
            bucket.append((member, float(score)))
        return len(mapping)

    def _expire(self, key, seconds):
        self.expires[key] = seconds
        return True

    async def zrange(self, key, start, stop, withscores=False):
        bucket = sorted(self.store.get(key, []), key=lambda x: x[1])
        window = bucket[start : stop + 1] if stop != -1 else bucket[start:]
        if withscores:
            return window
        return [m for m, _ in window]


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.mark.asyncio
async def test_allows_requests_under_limit(fake_redis):
    for _ in range(3):
        await rate_limiter.enforce_rate_limit(
            fake_redis,
            key="ratelimit:user:abc",
            limit=3,
            window_seconds=60,
            scope="user",
        )

    assert fake_redis._zcard("ratelimit:user:abc") == 3


@pytest.mark.asyncio
async def test_rejects_request_over_limit_with_429(fake_redis):
    for _ in range(3):
        await rate_limiter.enforce_rate_limit(
            fake_redis,
            key="ratelimit:user:abc",
            limit=3,
            window_seconds=60,
            scope="user",
        )

    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter.enforce_rate_limit(
            fake_redis,
            key="ratelimit:user:abc",
            limit=3,
            window_seconds=60,
            scope="user",
        )

    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.detail["scope"] == "user"
    assert exc.detail["retry_after_seconds"] >= 1
    assert "Retry-After" in exc.headers


@pytest.mark.asyncio
async def test_old_entries_are_evicted(fake_redis):
    # Hand-place 3 old entries outside the window.
    old_ts = time.time() - 120
    fake_redis.store["ratelimit:user:abc"] = [
        (f"{old_ts+i}", old_ts + i) for i in range(3)
    ]

    # Fresh request should pass despite the 3 stale entries.
    await rate_limiter.enforce_rate_limit(
        fake_redis,
        key="ratelimit:user:abc",
        limit=3,
        window_seconds=60,
        scope="user",
    )

    assert fake_redis._zcard("ratelimit:user:abc") == 1


@pytest.mark.asyncio
async def test_fails_open_when_redis_errors():
    class BrokenRedis:
        def pipeline(self):
            raise RuntimeError("redis down")

    # Must NOT raise — fail open.
    await rate_limiter.enforce_rate_limit(
        BrokenRedis(),
        key="ratelimit:user:abc",
        limit=1,
        window_seconds=60,
        scope="user",
    )


@pytest.mark.asyncio
async def test_per_user_and_per_ip_helpers_use_distinct_buckets(fake_redis):
    await rate_limiter.enforce_user_limit(fake_redis, user_id="u-1")
    await rate_limiter.enforce_ip_limit(fake_redis, ip="1.2.3.4")

    assert fake_redis._zcard("ratelimit:user:u-1") == 1
    assert fake_redis._zcard("ratelimit:ip:1.2.3.4") == 1
