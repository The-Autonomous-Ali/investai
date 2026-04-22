"""
Subscription routes for plan details, upgrades, and payment-webhook handling.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from models.models import Subscription, SubscriptionTier, User
from utils.auth import get_current_user

router = APIRouter()

# Monthly prices in paise (Razorpay uses paise, not rupees)
TIER_PRICES = {
    "starter": 99900,
    "pro": 209900,
    "elite": 419900,
}


class CreateSubscriptionRequest(BaseModel):
    tier: str  # starter, pro, elite


def _dev_bypass_enabled() -> bool:
    value = os.getenv("ALLOW_DEV_SUBSCRIPTION_BYPASS", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


@router.post("/create")
async def create_subscription(
    body: CreateSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate a subscription upgrade.

    In production, this should create a Razorpay subscription and return the
    payment link. Direct self-upgrades are disabled by default until verified
    payment integration is configured. Local development can opt in with
    ALLOW_DEV_SUBSCRIPTION_BYPASS=true.
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
                "Direct subscription upgrades are disabled until payment "
                "provider integration is configured. Set "
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
        "message": f"Upgraded to {body.tier}. Explicit local dev bypass is enabled.",
    }


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Razorpay webhook handler.

    TODO: Verify webhook signature in production.
    """
    body = await request.json()
    event = body.get("event", "")

    if event == "subscription.activated":
        pass
    elif event == "subscription.cancelled":
        pass
    elif event == "payment.failed":
        pass

    return {"status": "ok"}


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
