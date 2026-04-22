"""Sliding-window rate limiter backed by Redis sorted sets.

Usage (inside a FastAPI route)::

    await enforce_rate_limit(
        redis,
        key=f"ratelimit:user:{user.id}",
        limit=10,
        window_seconds=60,
        scope="user",
    )

Raises HTTPException(429) with a Retry-After header when the limit is
exceeded. Fails open on Redis errors so infra blips do not black-hole
real users; the monthly quota in `services.entitlements` remains the
hard ceiling on paid usage.
"""
from __future__ import annotations

import logging
import math
import os
import time

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

USER_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_USER_PER_MIN", "10"))
IP_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_IP_PER_MIN", "30"))
WINDOW_SECONDS = 60


async def enforce_rate_limit(
    redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    scope: str,
) -> None:
    """Allow or reject a request based on a Redis sliding window.

    Parameters
    ----------
    redis : redis.asyncio.Redis
        An async Redis client.
    key : str
        Bucket identifier, e.g. ``"ratelimit:user:<id>"``.
    limit : int
        Maximum requests allowed inside ``window_seconds``.
    window_seconds : int
        Sliding-window length.
    scope : str
        ``"user"`` or ``"ip"``; surfaced in the 429 body for debugging.
    """
    now = time.time()
    cutoff = now - window_seconds

    try:
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        _, current_count = await pipe.execute()
    except Exception as exc:  # noqa: BLE001 — any redis failure fails open
        logger.warning("rate_limiter: redis unavailable, failing open (%s)", exc)
        return

    if current_count >= limit:
        oldest_score = None
        try:
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_score = oldest[0][1]
        except Exception:  # noqa: BLE001
            oldest_score = None

        if oldest_score is not None:
            retry_after = max(1, math.ceil(oldest_score + window_seconds - now))
        else:
            retry_after = window_seconds

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Rate limit exceeded",
                "scope": scope,
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    try:
        pipe = redis.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window_seconds)
        await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("rate_limiter: failed to record hit (%s)", exc)


async def enforce_ip_limit(redis, ip: str) -> None:
    await enforce_rate_limit(
        redis,
        key=f"ratelimit:ip:{ip}",
        limit=IP_LIMIT_PER_MIN,
        window_seconds=WINDOW_SECONDS,
        scope="ip",
    )


async def enforce_user_limit(redis, user_id) -> None:
    await enforce_rate_limit(
        redis,
        key=f"ratelimit:user:{user_id}",
        limit=USER_LIMIT_PER_MIN,
        window_seconds=WINDOW_SECONDS,
        scope="user",
    )
