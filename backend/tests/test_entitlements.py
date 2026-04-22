from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.entitlements import consume_advice_quota, ensure_advice_quota, refresh_query_window


def build_user(*, tier="free", used=0, reset_date=None):
    return SimpleNamespace(
        subscription_tier=tier,
        queries_used_this_month=used,
        queries_reset_date=reset_date,
    )


def test_ensure_advice_quota_allows_free_user_under_limit():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    user = build_user(
        tier="free",
        used=2,
        reset_date=now + timedelta(days=10),
    )

    usage = ensure_advice_quota(user, now=now)

    assert usage["queries_limit"] == 3
    assert usage["queries_remaining"] == 1


def test_ensure_advice_quota_blocks_user_at_limit():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    user = build_user(
        tier="free",
        used=3,
        reset_date=now + timedelta(days=5),
    )

    with pytest.raises(HTTPException) as exc_info:
        ensure_advice_quota(user, now=now)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["usage"]["queries_remaining"] == 0


def test_refresh_query_window_resets_expired_usage():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    user = build_user(
        tier="starter",
        used=14,
        reset_date=now - timedelta(minutes=1),
    )

    changed = refresh_query_window(user, now=now)

    assert changed is True
    assert user.queries_used_this_month == 0
    assert user.queries_reset_date == now + timedelta(days=30)


def test_consume_advice_quota_increments_usage_and_reports_remaining():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    user = build_user(
        tier="starter",
        used=4,
        reset_date=now + timedelta(days=20),
    )

    usage = consume_advice_quota(user, now=now)

    assert user.queries_used_this_month == 5
    assert usage["queries_remaining"] == 25


def test_unlimited_tier_never_blocks_and_still_tracks_usage():
    now = datetime(2026, 4, 22, tzinfo=timezone.utc)
    user = build_user(
        tier="pro",
        used=99,
        reset_date=now + timedelta(days=20),
    )

    usage_before = ensure_advice_quota(user, now=now)
    usage_after = consume_advice_quota(user, now=now)

    assert usage_before["unlimited"] is True
    assert usage_before["queries_limit"] == -1
    assert usage_after["queries_used"] == 100
    assert usage_after["queries_remaining"] is None
