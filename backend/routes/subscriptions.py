"""
Subscription routes — plan listing, upgrade initiation, Razorpay webhook.

Tier upgrades only happen after Razorpay confirms payment via a signed
webhook. Direct self-upgrade is gated behind ALLOW_DEV_SUBSCRIPTION_BYPASS
for local-only testing.
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from models.models import Subscription, SubscriptionTier, User
from utils.auth import get_current_user

logger = structlog.get_logger()
router = APIRouter()

# Monthly prices in paise (Razorpay's smallest unit)
TIER_PRICES = {
    "starter": 99900,
    "pro": 209900,
    "elite": 419900,
}

# Plan-id pattern → tier mapping. Razorpay plans are created as
# plan_starter_monthly / plan_pro_monthly / plan_elite_monthly etc.
_PLAN_ID_TIER_MAP = (
    ("starter", "starter"),
    ("pro", "pro"),
    ("elite", "elite"),
)


class CreateSubscriptionRequest(BaseModel):
    tier: str  # starter, pro, elite


def _dev_bypass_enabled() -> bool:
    return os.getenv("ALLOW_DEV_SUBSCRIPTION_BYPASS", "").strip().lower() in {"1", "true", "yes", "on"}


def _verify_razorpay_signature(body_bytes: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _tier_from_plan_id(plan_id: str) -> str:
    plan_lower = (plan_id or "").lower()
    for needle, tier in _PLAN_ID_TIER_MAP:
        if needle in plan_lower:
            return tier
    return "starter"


# ── Read endpoints ───────────────────────────────────────────────────────────

@router.get("/current")
async def get_current_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's current subscription details."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()

    tier = user.subscription_tier.value if user.subscription_tier else "free"

    return {
        "tier": tier,
        "status": sub.status if sub else "active",
        "current_period_end": (
            sub.current_period_end.isoformat()
            if sub and sub.current_period_end
            else None
        ),
        "razorpay_sub_id": sub.razorpay_sub_id if sub else None,
        "features": _get_tier_features(tier),
    }


@router.get("/plans")
async def list_plans():
    """List all available subscription plans."""
    return {
        "plans": [
            {
                "tier": "free",
                "price": 0,
                "price_display": "Rs0",
                "period": "forever",
                "features": _get_tier_features("free"),
            },
            {
                "tier": "starter",
                "price": 999,
                "price_display": "Rs999",
                "period": "month",
                "features": _get_tier_features("starter"),
            },
            {
                "tier": "pro",
                "price": 2099,
                "price_display": "Rs2,099",
                "period": "month",
                "features": _get_tier_features("pro"),
                "popular": True,
            },
            {
                "tier": "elite",
                "price": 4199,
                "price_display": "Rs4,199",
                "period": "month",
                "features": _get_tier_features("elite"),
            },
        ]
    }


# ── Upgrade flow ─────────────────────────────────────────────────────────────

@router.post("/create")
async def create_subscription(
    body: CreateSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate a subscription upgrade.

    Production path: this should kick off a Razorpay subscription create call
    and return the payment link; the actual tier change happens once the
    `subscription.activated` webhook arrives (verified signature).

    Local path (ALLOW_DEV_SUBSCRIPTION_BYPASS=true) flips the tier directly
    so engineers can test gated features without a real payment.
    """
    if body.tier not in TIER_PRICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Choose: {', '.join(TIER_PRICES.keys())}",
        )

    if not _dev_bypass_enabled():
        raise HTTPException(
            status_code=501,
            detail=(
                "Direct subscription upgrades are disabled. Tier changes only "
                "happen via verified Razorpay webhook events. Set "
                "ALLOW_DEV_SUBSCRIPTION_BYPASS=true only in local development."
            ),
        )

    try:
        new_tier = SubscriptionTier(body.tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tier") from exc

    user.subscription_tier = new_tier
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()

    if sub:
        sub.tier = new_tier
        sub.status = "active"
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    else:
        sub = Subscription(
            user_id=user.id,
            tier=new_tier,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)

    user.queries_used_this_month = 0
    user.queries_reset_date = now + timedelta(days=30)

    await db.commit()

    return {
        "status": "active",
        "tier": body.tier,
        "message": f"Upgraded to {body.tier}. Local dev bypass is enabled.",
    }


# ── Webhook ──────────────────────────────────────────────────────────────────

@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Razorpay webhook handler with HMAC-SHA256 signature verification.

    Events handled:
      - subscription.activated  → upgrade user tier, set period window
      - subscription.cancelled  → mark sub cancelled, downgrade to free
      - payment.captured        → log only (no state change beyond activation)
      - payment.failed          → audit log only

    The handler ALWAYS verifies the X-Razorpay-Signature header against
    RAZORPAY_WEBHOOK_SECRET. Missing/empty secret in production is a
    misconfiguration and we reject all incoming webhooks rather than silently
    accept them.
    """
    body_bytes = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    if not secret:
        logger.error("razorpay.webhook_secret_not_configured")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    if not _verify_razorpay_signature(body_bytes, signature, secret):
        logger.warning("razorpay.invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = body.get("event", "")
    payload = body.get("payload", {})
    log = logger.bind(event=event)

    if event == "subscription.activated":
        sub_entity = payload.get("subscription", {}).get("entity", {})
        payment_entity = payload.get("payment", {}).get("entity", {})
        email = (payment_entity.get("email") or "").strip().lower()
        razorpay_sub_id = sub_entity.get("id")
        plan_id = sub_entity.get("plan_id", "")
        tier_str = _tier_from_plan_id(plan_id)

        if not email:
            log.warning("razorpay.activated_missing_email")
            return {"status": "ignored", "reason": "missing email"}

        try:
            new_tier = SubscriptionTier(tier_str)
        except ValueError:
            log.error("razorpay.unknown_tier", tier=tier_str)
            return {"status": "ignored", "reason": "unknown tier"}

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            log.warning("razorpay.user_not_found", email=email)
            return {"status": "ignored", "reason": "user not found"}

        user.subscription_tier = new_tier
        now = datetime.now(timezone.utc)
        user.queries_used_this_month = 0
        user.queries_reset_date = now + timedelta(days=30)

        existing = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        sub = existing.scalar_one_or_none()
        if sub:
            sub.tier = new_tier
            sub.status = "active"
            sub.razorpay_sub_id = razorpay_sub_id
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=30)
        else:
            db.add(
                Subscription(
                    user_id=user.id,
                    tier=new_tier,
                    status="active",
                    razorpay_sub_id=razorpay_sub_id,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                )
            )

        await db.commit()
        log.info("razorpay.subscription_activated", user_id=user.id, tier=tier_str)
        return {"status": "ok"}

    if event == "subscription.cancelled":
        sub_entity = payload.get("subscription", {}).get("entity", {})
        razorpay_sub_id = sub_entity.get("id")
        if not razorpay_sub_id:
            log.warning("razorpay.cancelled_missing_sub_id")
            return {"status": "ignored", "reason": "missing sub id"}

        result = await db.execute(
            select(Subscription).where(Subscription.razorpay_sub_id == razorpay_sub_id)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            log.warning("razorpay.sub_not_found", razorpay_sub_id=razorpay_sub_id)
            return {"status": "ignored", "reason": "subscription not found"}

        sub.status = "cancelled"
        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.subscription_tier = SubscriptionTier.FREE
        await db.commit()
        log.info("razorpay.subscription_cancelled", razorpay_sub_id=razorpay_sub_id)
        return {"status": "ok"}

    if event == "payment.captured":
        log.info("razorpay.payment_captured", payment_id=payload.get("payment", {}).get("entity", {}).get("id"))
        return {"status": "ok"}

    if event == "payment.failed":
        log.warning("razorpay.payment_failed", payload=payload.get("payment"))
        return {"status": "ok"}

    log.info("razorpay.event_ignored")
    return {"status": "ignored", "reason": f"unhandled event {event}"}


# ── Tier features ────────────────────────────────────────────────────────────

def _get_tier_features(tier: str) -> dict:
    features = {
        "free": {
            "queries_per_month": 3,
            "memory_months": 0,
            "signal_sources": ["news"],
            "tax_optimization": False,
            "real_time_alerts": False,
            "portfolio_tracking": False,
            "max_portfolio_items": 5,
        },
        "starter": {
            "queries_per_month": 30,
            "memory_months": 3,
            "signal_sources": ["news", "market_data"],
            "tax_optimization": "basic",
            "real_time_alerts": False,
            "portfolio_tracking": True,
            "max_portfolio_items": -1,
        },
        "pro": {
            "queries_per_month": -1,
            "memory_months": 12,
            "signal_sources": ["news", "market_data", "twitter"],
            "tax_optimization": "full",
            "real_time_alerts": True,
            "portfolio_tracking": True,
            "max_portfolio_items": -1,
        },
        "elite": {
            "queries_per_month": -1,
            "memory_months": -1,
            "signal_sources": ["news", "market_data", "twitter", "linkedin"],
            "tax_optimization": "full_with_ca_review",
            "real_time_alerts": True,
            "portfolio_tracking": True,
            "max_portfolio_items": -1,
            "api_access": True,
        },
    }
    return features.get(tier, features["free"])
