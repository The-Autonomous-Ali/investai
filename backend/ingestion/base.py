"""BaseConnector — abstract parent for every ingestion source.

Every feed (RSS, REST API, yfinance, HTML scrape) subclasses this to get:
- Common content-hash dedup (in-memory cache + Redis SET + Postgres unique
  constraint — three layers, belt-and-braces)
- Standardized message shape on the stream
- Structured logging tagged with connector name
- Health-status tracking (last_run, last_success, consecutive_failures)

Subclass contract: override `fetch()` to yield `RawSignal` objects.
Everything else — dedup, emit, error handling — is provided.

The dedup strategy is OPTIMISTIC: if Redis is down or the in-memory
cache is cold, duplicates may briefly slip through to the stream. The
signal_extractor consumer is authoritative — it checks the Postgres
unique index on content_hash and skips duplicates there. The upstream
layers are optimizations, not the source of truth.
"""
from __future__ import annotations

import abc
import hashlib
import json
import structlog
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from ingestion.redis_client import get_client

logger = structlog.get_logger()

# How many recent hashes each connector remembers in-process.
# Redis SET is the cross-process layer; this is the cheapest first check.
HASH_CACHE_SIZE = 10_000

# Redis key + TTL for cross-process dedup. TTL is longer than the
# expected re-publish window of any source; 7 days is generous.
DEDUP_SET_KEY = "ingestion:seen_hashes"
DEDUP_TTL_SECONDS = 7 * 24 * 3600


@dataclass
class RawSignal:
    """One raw item pulled from an external source.

    This is the shape pushed into the `signals.raw` Redis Stream.
    The signal_extractor consumer reads this, runs LLM extraction,
    and writes the enriched result to the `signals` Postgres table.

    Fields are deliberately flat (no nested dicts) so Redis Streams
    can store them as a simple hash-map without JSON-in-JSON nesting.
    Complex data like `raw_payload` is JSON-encoded once.
    """

    source_name: str           # "fed", "rbi", "nsdl-fpi", "yfinance:^NSEI"
    source_region: str         # us | eu | uk | jp | cn | in | global
    source_tier: int           # 1 (official) | 2 (major media) | 3 (secondary)
    category: str              # monetary | regulatory | markets | corporate | commodities | capital_flow | macro | price
    url: str                   # canonical URL for this item
    title: str
    body: str                  # raw content (pre-LLM)
    fetched_at: str = ""       # ISO8601; set by __post_init__ if empty
    published_at: Optional[str] = None  # ISO8601 if source provides it
    raw_payload: Optional[str] = None   # JSON-encoded extras (price dict, structured data)
    content_hash: str = ""     # sha256 of (source_name + url + title); set by __post_init__

    def __post_init__(self) -> None:
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        material = f"{self.source_name}|{self.url}|{self.title}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def to_stream_fields(self) -> dict[str, str]:
        """Flatten for XADD. Redis Stream fields must be strings."""
        d = asdict(self)
        # raw_payload is already a JSON string or None. Everything else is
        # either a string or a small scalar — stringify them.
        return {k: ("" if v is None else str(v)) for k, v in d.items()}


class BaseConnector(abc.ABC):
    """Subclass and implement `fetch()`. Call `run()` to execute one pass."""

    name: str = "base"               # override
    region: str = "global"           # override
    tier: int = 3                    # override; 1 most authoritative
    category: str = "markets"        # override

    def __init__(self) -> None:
        self._recent_hashes: deque[str] = deque(maxlen=HASH_CACHE_SIZE)
        self._hash_set: set[str] = set()
        self.last_run_at: Optional[datetime] = None
        self.last_success_at: Optional[datetime] = None
        self.consecutive_failures: int = 0
        self._log = logger.bind(connector=self.name)

    @abc.abstractmethod
    async def fetch(self) -> AsyncIterator[RawSignal]:
        """Yield RawSignal objects. Must be an async generator.

        Implementations should NOT dedup — base class handles it.
        Implementations SHOULD catch per-item parse errors and keep going,
        rather than letting one malformed item kill a batch.
        """
        # The following line is never executed — it just tells the type
        # checker this is an async generator. Subclasses provide real bodies.
        if False:
            yield  # pragma: no cover

    async def run(self) -> int:
        """One execution pass. Returns number of NEW signals emitted.

        Never raises — all exceptions are logged and counted as failures.
        Never blocks on Redis errors — RedisStreamClient swallows those.
        """
        self.last_run_at = datetime.now(timezone.utc)
        redis = get_client()
        new_count = 0

        try:
            async for item in self.fetch():
                if await self._is_duplicate(item.content_hash, redis):
                    continue

                fields = item.to_stream_fields()
                msg_id = await redis.xadd(fields)

                if msg_id is not None:
                    await self._remember(item.content_hash, redis)
                    new_count += 1

            self.last_success_at = datetime.now(timezone.utc)
            self.consecutive_failures = 0
            self._log.info(
                "connector.run.success",
                new_signals=new_count,
            )
            return new_count

        except Exception as e:
            self.consecutive_failures += 1
            self._log.warning(
                "connector.run.failed",
                error=str(e),
                consecutive_failures=self.consecutive_failures,
            )
            return new_count

    async def _is_duplicate(self, content_hash: str, redis) -> bool:
        """Three-layer check: in-memory -> Redis SET -> (Postgres is final gate).

        Returns True if this hash was seen recently. The Postgres unique
        constraint on content_hash is the ultimate authority; these two
        upstream layers just save downstream work.
        """
        if content_hash in self._hash_set:
            return True

        # Cross-process dedup via Redis SET. SISMEMBER is O(1).
        await redis.connect()
        try:
            seen = await redis._redis.sismember(DEDUP_SET_KEY, content_hash)
            return bool(seen)
        except Exception:
            # Redis down = we don't know. Assume not a duplicate; Postgres
            # unique constraint will reject it downstream if it is.
            return False

    async def _remember(self, content_hash: str, redis) -> None:
        """Record this hash in both in-memory cache and Redis SET."""
        if len(self._recent_hashes) == self._recent_hashes.maxlen:
            # Evict the oldest from the set too
            oldest = self._recent_hashes[0]
            self._hash_set.discard(oldest)
        self._recent_hashes.append(content_hash)
        self._hash_set.add(content_hash)

        await redis.connect()
        try:
            await redis._redis.sadd(DEDUP_SET_KEY, content_hash)
            # Reset TTL on every write — cheap, keeps hot items alive
            await redis._redis.expire(DEDUP_SET_KEY, DEDUP_TTL_SECONDS)
        except Exception:
            pass  # optimization only; Postgres is the source of truth

    def health_status(self) -> dict[str, object]:
        """Snapshot for /api/health and monitoring dashboards."""
        return {
            "name": self.name,
            "region": self.region,
            "tier": self.tier,
            "category": self.category,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "consecutive_failures": self.consecutive_failures,
            "healthy": self.consecutive_failures < 3,
        }
