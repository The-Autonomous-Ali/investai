from datetime import datetime, timedelta, timezone
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.models import SubscriptionTier


async def _noop_dependency():
    return None


fake_db_connection = ModuleType("database.connection")
fake_db_connection.get_db = _noop_dependency
sys.modules.setdefault("database.connection", fake_db_connection)

fake_auth = ModuleType("utils.auth")
fake_auth.get_current_user = _noop_dependency
sys.modules.setdefault("utils.auth", fake_auth)

from routes.subscriptions import CreateSubscriptionRequest, create_subscription


def build_user():
    return SimpleNamespace(
        id="user-1",
        subscription_tier=SubscriptionTier.FREE,
        queries_used_this_month=7,
        queries_reset_date=None,
    )


def build_db(existing_subscription=None):
    result = SimpleNamespace(
        scalar_one_or_none=MagicMock(return_value=existing_subscription)
    )
    return SimpleNamespace(
        execute=AsyncMock(return_value=result),
        add=MagicMock(),
        commit=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_create_subscription_is_disabled_without_explicit_dev_bypass(monkeypatch):
    monkeypatch.delenv("ALLOW_DEV_SUBSCRIPTION_BYPASS", raising=False)
    user = build_user()
    db = build_db()

    with pytest.raises(HTTPException) as exc_info:
        await create_subscription(CreateSubscriptionRequest(tier="starter"), user, db)

    assert exc_info.value.status_code == 501
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subscription_allows_explicit_local_dev_bypass(monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_SUBSCRIPTION_BYPASS", "true")
    user = build_user()
    db = build_db()
    before = datetime.now(timezone.utc)

    response = await create_subscription(CreateSubscriptionRequest(tier="starter"), user, db)

    assert response["status"] == "active"
    assert response["tier"] == "starter"
    assert user.subscription_tier == SubscriptionTier.STARTER
    assert user.queries_used_this_month == 0
    assert user.queries_reset_date >= before + timedelta(days=29)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
