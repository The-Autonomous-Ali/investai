"""Async Redis wrapper for the ingestion Streams pipeline.

Thin layer on top of `redis.asyncio` that:
- Manages a single connection pool for the whole process
- Exposes Stream-specific helpers (xadd, xread_group, xack, ensure_group)
- Never raises on Redis being down — callers get empty results and can retry;
  feed outages must not cascade into reasoning-layer outages

Stream name: `signals.raw` — partitioning by source_region is done via the
`region` field on the message, not separate streams, so one consumer group
sees the full global view.
"""
from __future__ import annotations

import os
import structlog
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import RedisError, ResponseError

logger = structlog.get_logger()

STREAM_NAME = "signals.raw"
CONSUMER_GROUP = "signal-extractor"
DEFAULT_MAXLEN = 100_000  # approximate cap; Redis uses ~MAXLEN for efficiency


class RedisStreamClient:
    """Singleton-style wrapper. Use `get_client()` module-level accessor."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def ping(self) -> bool:
        await self.connect()
        try:
            return bool(await self._redis.ping())
        except RedisError as e:
            logger.warning("redis.ping.failed", error=str(e))
            return False

    async def xadd(
        self,
        fields: dict[str, str],
        stream: str = STREAM_NAME,
        maxlen: int = DEFAULT_MAXLEN,
    ) -> Optional[str]:
        """Append a message to the stream. Returns the message ID, or None on failure.

        Uses approximate MAXLEN (~) for O(1) trimming. Stream grows slightly past
        the limit but never unboundedly.
        """
        await self.connect()
        try:
            msg_id = await self._redis.xadd(
                stream, fields, maxlen=maxlen, approximate=True
            )
            return msg_id
        except RedisError as e:
            logger.warning("redis.xadd.failed", stream=stream, error=str(e))
            return None

    async def ensure_group(
        self,
        stream: str = STREAM_NAME,
        group: str = CONSUMER_GROUP,
    ) -> None:
        """Create the consumer group if it doesn't exist. Idempotent."""
        await self.connect()
        try:
            await self._redis.xgroup_create(
                stream, group, id="0", mkstream=True
            )
            logger.info("redis.group.created", stream=stream, group=group)
        except ResponseError as e:
            # BUSYGROUP = already exists. Anything else is a real error.
            if "BUSYGROUP" in str(e):
                return
            logger.warning("redis.group.create_failed", error=str(e))

    async def xread_group(
        self,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
        stream: str = STREAM_NAME,
        group: str = CONSUMER_GROUP,
    ) -> list[tuple[str, dict[str, str]]]:
        """Read pending messages for this consumer. Returns list of (msg_id, fields)."""
        await self.connect()
        try:
            result = await self._redis.xreadgroup(
                group,
                consumer,
                {stream: ">"},
                count=count,
                block=block_ms,
            )
            if not result:
                return []
            # result shape: [[stream_name, [(msg_id, {fields}), ...]]]
            _, messages = result[0]
            return messages
        except RedisError as e:
            logger.warning("redis.xread.failed", error=str(e))
            return []

    async def xack(
        self,
        msg_id: str,
        stream: str = STREAM_NAME,
        group: str = CONSUMER_GROUP,
    ) -> bool:
        """Acknowledge a message. Returns True on success."""
        await self.connect()
        try:
            acked = await self._redis.xack(stream, group, msg_id)
            return acked == 1
        except RedisError as e:
            logger.warning("redis.xack.failed", msg_id=msg_id, error=str(e))
            return False

    async def stream_length(self, stream: str = STREAM_NAME) -> int:
        """Return current stream length (0 if missing or error)."""
        await self.connect()
        try:
            return await self._redis.xlen(stream)
        except RedisError:
            return 0


_client: Optional[RedisStreamClient] = None


def get_client() -> RedisStreamClient:
    """Module-level accessor. Honors REDIS_URL env; defaults to localhost."""
    global _client
    if _client is None:
        _client = RedisStreamClient(
            os.getenv("REDIS_URL", "redis://localhost:6379")
        )
    return _client


async def reset_client_for_testing() -> None:
    """Close and clear the module-level client. Test-only."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
