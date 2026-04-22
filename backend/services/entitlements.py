"""Quota and entitlement helpers for user-facing API routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

RESET_WINDOW_DAYS = 30

TIER_QUERY_LIMITS = {
    "free": 3,
    "starter": 30,
    "pro": -1,
    "elite": -1,
}


def get_subscription_tier(user) -> str:
    tier = getattr(user, "subscription_tier", None)
    return tier.value if hasattr(tier, "value") else (tier or "free")


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def refresh_query_window(user, now: datetime | None = None) -> bool:
    """Reset usage counters when the current billing window has expired."""
    now = normalize_datetime(now) or datetime.now(timezone.utc)
    reset_date = normalize_datetime(getattr(user, "queries_reset_date", None))
    used = getattr(user, "queries_used_this_month", 0) or 0

    if reset_date is None or reset_date <= now:
        user.queries_used_this_month = 0
        user.queries_reset_date = now + timedelta(days=RESET_WINDOW_DAYS)
        return used != 0 or reset_date is None

    return False


def get_usage_snapshot(user) -> dict:
    tier = get_subscription_tier(user)
    limit = TIER_QUERY_LIMITS.get(tier, TIER_QUERY_LIMITS["free"])
    used = getattr(user, "queries_used_this_month", 0) or 0
    reset_date = normalize_datetime(getattr(user, "queries_reset_date", None))
    remaining = None if limit == -1 else max(limit - used, 0)

    return {
        "tier": tier,
        "queries_used": used,
        "queries_limit": limit,
        "queries_remaining": remaining,
        "unlimited": limit == -1,
        "reset_date": reset_date.isoformat() if reset_date else None,
    }


def ensure_advice_quota(user, now: datetime | None = None) -> dict:
    """Raise 403 when the user has exhausted their plan quota."""
    refresh_query_window(user, now=now)
    usage = get_usage_snapshot(user)

    if not usage["unlimited"] and usage["queries_used"] >= usage["queries_limit"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Monthly advice quota reached for the current subscription tier.",
                "usage": usage,
            },
        )

    return usage


def consume_advice_quota(user, now: datetime | None = None) -> dict:
    """Increment billable usage after a successful advice response."""
    refresh_query_window(user, now=now)
    user.queries_used_this_month = (getattr(user, "queries_used_this_month", 0) or 0) + 1
    return get_usage_snapshot(user)
