"""
Signal routes — serve detected market signals to the frontend.

Signals are created by the SignalWatcher agent (runs every 15 min via worker).
This route just reads and filters them from the database.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from typing import Optional
from datetime import datetime, timedelta, timezone

from database.connection import get_db
from models.models import Signal, User
from utils.auth import get_current_user

router = APIRouter()


@router.get("/")
async def list_signals(
    signal_type: Optional[str] = Query(None, description="Filter: geopolitical, monetary, fiscal, commodity, etc."),
    urgency: Optional[str] = Query(None, description="Filter: breaking, developing, long_term"),
    geography: Optional[str] = Query(None, description="Filter: global, india"),
    min_importance: float = Query(0.0, description="Minimum importance score (0-10)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List active signals, ordered by importance.
    Free tier only sees top 5; paid tiers get full list.
    """
    query = select(Signal).where(
        Signal.importance_score >= min_importance,
    ).order_by(desc(Signal.importance_score), desc(Signal.detected_at))

    if signal_type:
        query = query.where(Signal.signal_type == signal_type)
    if urgency:
        query = query.where(Signal.urgency == urgency)
    if geography:
        query = query.where(Signal.geography == geography)

    # Free tier: limited signals
    tier = user.subscription_tier.value if user.subscription_tier else "free"
    if tier == "free":
        limit = min(limit, 5)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    signals = result.scalars().all()

    return {
        "signals": [_serialize_signal(s) for s in signals],
        "count": len(signals),
        "tier": tier,
    }


@router.get("/active")
async def get_active_signals(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get currently active/escalating signals — the most urgent ones."""
    result = await db.execute(
        select(Signal)
        .where(Signal.stage.in_(["active", "escalating", "alert"]))
        .order_by(desc(Signal.importance_score))
        .limit(10)
    )
    signals = result.scalars().all()
    return {"signals": [_serialize_signal(s) for s in signals]}


@router.get("/{signal_id}")
async def get_signal_detail(
    signal_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full detail for a single signal including chain effects and lifecycle."""
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Signal not found")

    return _serialize_signal(signal, full=True)


@router.get("/{signal_id}/timeline")
async def get_signal_timeline(
    signal_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get lifecycle timeline for a signal — how it evolved over time."""
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Signal not found")

    return {
        "signal_id": signal.id,
        "title": signal.title,
        "current_stage": signal.stage.value if signal.stage else "watch",
        "lifecycle_data": signal.lifecycle_data or {},
        "resolution_conditions": signal.resolution_conditions or [],
        "probability_scenarios": signal.probability_scenarios or {},
        "early_warning_signals": signal.early_warning_signals or {},
        "detected_at": signal.detected_at.isoformat() if signal.detected_at else None,
    }


def _serialize_signal(signal: Signal, full: bool = False) -> dict:
    """Convert Signal ORM object to API response dict."""
    data = {
        "id": signal.id,
        "title": signal.title,
        "source": signal.source,
        "source_tier": signal.source_tier,
        "signal_type": signal.signal_type.value if signal.signal_type else None,
        "urgency": signal.urgency.value if signal.urgency else None,
        "importance_score": signal.importance_score,
        "confidence": signal.confidence,
        "geography": signal.geography,
        "sentiment": signal.sentiment,
        "sectors_affected": signal.sectors_affected or {},
        "stage": signal.stage.value if signal.stage else "watch",
        "corroborated_by": signal.corroborated_by or [],
        "detected_at": signal.detected_at.isoformat() if signal.detected_at else None,
    }
    if full:
        data.update({
            "content": signal.content,
            "entities_mentioned": signal.entities_mentioned or [],
            "india_impact_analysis": signal.india_impact_analysis,
            "chain_effects": signal.chain_effects or [],
            "lifecycle_data": signal.lifecycle_data or {},
            "resolution_conditions": signal.resolution_conditions or [],
            "probability_scenarios": signal.probability_scenarios or {},
        })
    return data
