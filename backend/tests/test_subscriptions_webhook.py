"""Razorpay webhook signature verification + activation/cancellation flow."""
import hashlib
import hmac
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


async def _noop_dependency():
    return None


fake_db_connection = ModuleType("database.connection")
fake_db_connection.get_db = _noop_dependency
sys.modules.setdefault("database.connection", fake_db_connection)

fake_auth = ModuleType("utils.auth")
fake_auth.get_current_user = _noop_dependency
sys.modules.setdefault("utils.auth", fake_auth)

import routes.subscriptions as subs_module
from routes.subscriptions import _tier_from_plan_id, _verify_razorpay_signature, router


WEBHOOK_SECRET = "test_secret_xyz"


def _sign(body_bytes: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


def _build_app(stub_user=None, stub_sub=None):
    app = FastAPI()

    user_state = {"current": stub_user, "current_sub": stub_sub}

    async def _override_db():
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        async def execute(stmt):
            sql = str(stmt).lower()
            result = MagicMock()
            if "subscriptions" in sql:
                result.scalar_one_or_none = MagicMock(return_value=user_state["current_sub"])
            else:
                result.scalar_one_or_none = MagicMock(return_value=user_state["current"])
            return result

        session.execute = AsyncMock(side_effect=execute)
        yield session

    app.dependency_overrides[subs_module.get_db] = _override_db
    app.include_router(router, prefix="/api/subscriptions")
    return app


# ── Pure signature helper ────────────────────────────────────────────────────

def test_signature_helper_accepts_valid_signature():
    body = b'{"event":"subscription.activated"}'
    sig = _sign(body)
    assert _verify_razorpay_signature(body, sig, WEBHOOK_SECRET) is True


def test_signature_helper_rejects_tampered_body():
    body = b'{"event":"subscription.activated"}'
    sig = _sign(body)
    tampered = b'{"event":"subscription.cancelled"}'
    assert _verify_razorpay_signature(tampered, sig, WEBHOOK_SECRET) is False


def test_signature_helper_rejects_empty_signature():
    body = b'{"event":"x"}'
    assert _verify_razorpay_signature(body, "", WEBHOOK_SECRET) is False


def test_signature_helper_rejects_missing_secret():
    body = b'{"event":"x"}'
    sig = _sign(body)
    assert _verify_razorpay_signature(body, sig, "") is False


# ── Plan-id → tier mapping ───────────────────────────────────────────────────

@pytest.mark.parametrize("plan_id,expected", [
    ("plan_starter_monthly", "starter"),
    ("plan_pro_quarterly", "pro"),
    ("plan_elite_yearly", "elite"),
    ("PLAN_PRO_2026", "pro"),
    ("plan_unknown", "starter"),  # fallback
    ("", "starter"),
    (None, "starter"),
])
def test_tier_from_plan_id(plan_id, expected):
    assert _tier_from_plan_id(plan_id) == expected


# ── Webhook endpoint ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_rejects_when_secret_not_configured(monkeypatch):
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    app = _build_app()
    body = json.dumps({"event": "subscription.activated"}).encode()

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/subscriptions/webhook/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": "anything"},
        )

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    app = _build_app()
    body = json.dumps({"event": "subscription.activated"}).encode()

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/subscriptions/webhook/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": "deadbeef"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signature_and_activates(monkeypatch):
    from models.models import SubscriptionTier

    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    user = SimpleNamespace(
        id="user-1",
        email="payer@example.com",
        subscription_tier=SubscriptionTier.FREE,
        queries_used_this_month=0,
        queries_reset_date=None,
    )
    app = _build_app(stub_user=user, stub_sub=None)

    body = json.dumps({
        "event": "subscription.activated",
        "payload": {
            "subscription": {"entity": {"id": "sub_RZ_123", "plan_id": "plan_pro_monthly"}},
            "payment": {"entity": {"email": "payer@example.com"}},
        },
    }).encode()
    sig = _sign(body)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/subscriptions/webhook/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": sig, "content-type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    # Tier was actually upgraded on the user object
    assert user.subscription_tier == SubscriptionTier.PRO


@pytest.mark.asyncio
async def test_webhook_handles_payment_failed(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    app = _build_app()
    body = json.dumps({
        "event": "payment.failed",
        "payload": {"payment": {"entity": {"id": "pay_X"}}},
    }).encode()
    sig = _sign(body)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/subscriptions/webhook/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": sig},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_unknown_event_is_ignored(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    app = _build_app()
    body = json.dumps({"event": "order.notified"}).encode()
    sig = _sign(body)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/subscriptions/webhook/razorpay",
            content=body,
            headers={"X-Razorpay-Signature": sig},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
