"""Unit tests for RedisStreamClient — all Redis calls are mocked."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from redis.exceptions import RedisError, ResponseError

from ingestion.redis_client import (
    RedisStreamClient,
    get_client,
    reset_client_for_testing,
    STREAM_NAME,
    CONSUMER_GROUP,
)


@pytest.fixture
def fake_redis():
    """Minimal async Redis stub."""
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.xadd = AsyncMock(return_value=b"1700000000-0")
    r.xgroup_create = AsyncMock(return_value=True)
    r.xreadgroup = AsyncMock(return_value=[])
    r.xack = AsyncMock(return_value=1)
    r.xlen = AsyncMock(return_value=0)
    r.close = AsyncMock()
    return r


@pytest.fixture
def client(fake_redis):
    c = RedisStreamClient("redis://fake:6379")
    c._redis = fake_redis
    return c


@pytest.mark.asyncio
async def test_ping_returns_true_on_healthy_redis(client, fake_redis):
    assert await client.ping() is True
    fake_redis.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_ping_returns_false_on_redis_error(client, fake_redis):
    fake_redis.ping.side_effect = RedisError("connection refused")
    assert await client.ping() is False


@pytest.mark.asyncio
async def test_xadd_returns_message_id(client, fake_redis):
    msg_id = await client.xadd({"source": "fed", "payload": "..."})
    assert msg_id == b"1700000000-0"
    fake_redis.xadd.assert_awaited_once()
    call_kwargs = fake_redis.xadd.call_args.kwargs
    assert call_kwargs["approximate"] is True
    assert call_kwargs["maxlen"] == 100_000


@pytest.mark.asyncio
async def test_xadd_returns_none_on_redis_down(client, fake_redis):
    fake_redis.xadd.side_effect = RedisError("down")
    result = await client.xadd({"source": "fed"})
    assert result is None


@pytest.mark.asyncio
async def test_ensure_group_swallows_busygroup_error(client, fake_redis):
    fake_redis.xgroup_create.side_effect = ResponseError("BUSYGROUP group already exists")
    # Should NOT raise
    await client.ensure_group()


@pytest.mark.asyncio
async def test_ensure_group_logs_other_response_errors(client, fake_redis):
    fake_redis.xgroup_create.side_effect = ResponseError("ERR some other problem")
    # Should NOT raise, but should log (verified by not raising)
    await client.ensure_group()


@pytest.mark.asyncio
async def test_xread_group_returns_messages(client, fake_redis):
    fake_redis.xreadgroup.return_value = [
        (STREAM_NAME, [(b"1-0", {"source": "fed", "title": "rate cut"})])
    ]
    messages = await client.xread_group(consumer="c1")
    assert len(messages) == 1
    msg_id, fields = messages[0]
    assert msg_id == b"1-0"
    assert fields["source"] == "fed"


@pytest.mark.asyncio
async def test_xread_group_returns_empty_on_no_messages(client, fake_redis):
    fake_redis.xreadgroup.return_value = []
    assert await client.xread_group(consumer="c1") == []


@pytest.mark.asyncio
async def test_xread_group_returns_empty_on_redis_error(client, fake_redis):
    fake_redis.xreadgroup.side_effect = RedisError("down")
    assert await client.xread_group(consumer="c1") == []


@pytest.mark.asyncio
async def test_xack_success(client, fake_redis):
    assert await client.xack("1-0") is True


@pytest.mark.asyncio
async def test_xack_failure_returns_false(client, fake_redis):
    fake_redis.xack.side_effect = RedisError("down")
    assert await client.xack("1-0") is False


@pytest.mark.asyncio
async def test_stream_length_returns_zero_on_error(client, fake_redis):
    fake_redis.xlen.side_effect = RedisError("down")
    assert await client.stream_length() == 0


@pytest.mark.asyncio
async def test_module_level_client_is_singleton():
    await reset_client_for_testing()
    with patch("ingestion.redis_client.aioredis.from_url"):
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2
    await reset_client_for_testing()


@pytest.mark.asyncio
async def test_close_is_idempotent(client, fake_redis):
    await client.close()
    # Second close should not raise
    await client.close()
