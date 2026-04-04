"""
Subscription routes — manage tier upgrades and Razorpay integration.

Tier limits are enforced across the app:
- Free: 3 queries/month, 5 portfolio items, no memory
- Starter: 30 queries/month, unlimited portfolio, 3 month memory
- Pro: Unlimited queries, all sources, real-time alerts
- Elite: Everything + LinkedIn signals + API access
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone

from database.connection import get_db
from models.models import User, Subscription, SubscriptionTier
from utils.auth import get_current_user

router = APIRouter()

# Monthly prices in paise (Razorpay uses paise, not rupees)
TIER_PRICES = {
    "starter": 99900,   # ₹999
    "pro": 209900,      # ₹2,099
    "elite": 419900,    # ₹4,199
}


class CreateSubscriptionRequest(BaseModel):
    tier: str  # starter, pro, elite


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
        "status": sub.status if sub else "active",  # free is always active
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
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
                "price_display": "₹0",
                "period": "forever",
                "features": _get_tier_features("free"),
            },
            {
                "tier": "starter",
                "price": 999,
                "price_display": "₹999",
                "period": "month",
                "features": _get_tier_features("starter"),
            },
            {
                "tier": "pro",
                "price": 2099,
                "price_display": "₹2,099",
                "period": "month",
                "features": _get_tier_features("pro"),
                "popular": True,
            },
            {
                "tier": "elite",
                "price": 4199,
                "price_display": "₹4,199",
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
    In production, this creates a Razorpay subscription and returns the payment link.
    For now, it directly upgrades the tier (dev mode).
    """
    if body.tier not in TIER_PRICES:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Choose: {', '.join(TIER_PRICES.keys())}")

    # TODO: In production, create Razorpay subscription here
    # razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    # subscription = razorpay_client.subscription.create({...})

    # Dev mode: directly upgrade
    try:
        new_tier = SubscriptionTier(body.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tier")

    user.subscription_tier = new_tier
    now = datetime.now(timezone.utc)

    # Create or update subscription record
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

    # Reset query count on upgrade
    user.queries_used_this_month = 0
    user.queries_reset_date = now + timedelta(days=30)

    await db.commit()

    return {
        "status": "active",
        "tier": body.tier,
        "message": f"Upgraded to {body.tier}. Dev mode — no payment required.",
    }


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Razorpay webhook handler — called by Razorpay on payment events.
    TODO: Verify webhook signature in production.
    """
    body = await request.json()
    event = body.get("event", "")

    if event == "subscription.activated":
        # Payment successful — activate subscription
        pass
    elif event == "subscription.cancelled":
        # User cancelled — downgrade at period end
        pass
    elif event == "payment.failed":
        # Payment failed — notify user
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
