"""
User profile routes — view and update preferences.
These preferences feed directly into the AI agents:
- risk_tolerance → affects allocation aggressiveness
- avoid_sectors → filters out sectors user doesn't want
- tax_bracket → enables tax optimization
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from database.connection import get_db
from models.models import User, RiskTolerance
from utils.auth import get_current_user

router = APIRouter()


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    risk_tolerance: Optional[str] = None
    investment_horizon: Optional[str] = None
    monthly_income_bracket: Optional[str] = None
    tax_bracket: Optional[int] = None
    country: Optional[str] = None
    state: Optional[str] = None
    experience_level: Optional[str] = None
    avoid_sectors: Optional[list[str]] = None
    preferred_instruments: Optional[list[str]] = None
    notification_prefs: Optional[dict] = None


@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    """Return full user profile."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "risk_tolerance": user.risk_tolerance.value if user.risk_tolerance else "moderate",
        "investment_horizon": user.investment_horizon,
        "monthly_income_bracket": user.monthly_income_bracket,
        "tax_bracket": user.tax_bracket,
        "country": user.country,
        "state": user.state,
        "experience_level": user.experience_level,
        "avoid_sectors": user.avoid_sectors or [],
        "preferred_instruments": user.preferred_instruments or [],
        "notification_prefs": user.notification_prefs or {},
        "subscription_tier": user.subscription_tier.value if user.subscription_tier else "free",
        "queries_used_this_month": user.queries_used_this_month or 0,
        "linkedin_connected": user.linkedin_connected,
        "twitter_connected": user.twitter_connected,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.patch("/profile")
async def update_profile(
    updates: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user preferences. Only provided fields are updated."""
    update_data = updates.model_dump(exclude_none=True)

    # Validate risk_tolerance enum
    if "risk_tolerance" in update_data:
        try:
            update_data["risk_tolerance"] = RiskTolerance(update_data["risk_tolerance"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid risk_tolerance. Use: conservative, moderate, aggressive")

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    return {"status": "updated", "fields": list(update_data.keys())}


@router.get("/usage")
async def get_usage(user: User = Depends(get_current_user)):
    """Return query usage for current billing period."""
    tier_limits = {
        "free": 3,
        "starter": 30,
        "pro": -1,    # unlimited
        "elite": -1,  # unlimited
    }
    tier = user.subscription_tier.value if user.subscription_tier else "free"
    limit = tier_limits.get(tier, 3)

    return {
        "tier": tier,
        "queries_used": user.queries_used_this_month or 0,
        "queries_limit": limit,
        "unlimited": limit == -1,
        "reset_date": user.queries_reset_date.isoformat() if user.queries_reset_date else None,
    }
