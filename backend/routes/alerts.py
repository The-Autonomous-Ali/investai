"""
Alert routes — user notifications for signals, portfolio actions, and triggers.

Alerts are created by:
- Signal Watcher (new breaking signals)
- Portfolio Agent (rebalancing triggers)
- Temporal Agent (event stage changes)
- Worker (scheduled performance updates)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, func
from typing import Optional

from database.connection import get_db
from models.models import User, UserAlert
from utils.auth import get_current_user

router = APIRouter()


@router.get("/")
async def list_alerts(
    unread_only: bool = Query(False, description="Only show unread alerts"),
    severity: Optional[str] = Query(None, description="Filter: info, warning, urgent"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List alerts for the current user, newest first."""
    query = select(UserAlert).where(UserAlert.user_id == user.id)

    if unread_only:
        query = query.where(UserAlert.is_read == False)
    if severity:
        query = query.where(UserAlert.severity == severity)

    query = query.order_by(desc(UserAlert.created_at)).offset(offset).limit(limit)

    result = await db.execute(query)
    alerts = result.scalars().all()

    # Also get unread count
    count_result = await db.execute(
        select(func.count(UserAlert.id)).where(
            UserAlert.user_id == user.id,
            UserAlert.is_read == False,
        )
    )
    unread_count = count_result.scalar() or 0

    return {
        "alerts": [_serialize_alert(a) for a in alerts],
        "unread_count": unread_count,
    }


@router.patch("/{alert_id}/read")
async def mark_alert_read(
    alert_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single alert as read."""
    result = await db.execute(
        select(UserAlert).where(
            UserAlert.id == alert_id,
            UserAlert.user_id == user.id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_read = True
    await db.commit()
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all alerts as read for the current user."""
    await db.execute(
        update(UserAlert)
        .where(UserAlert.user_id == user.id, UserAlert.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"status": "all_read"}


def _serialize_alert(alert: UserAlert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "title": alert.title,
        "message": alert.message,
        "severity": alert.severity,
        "is_read": alert.is_read,
        "action_required": alert.action_required,
        "signal_id": alert.signal_id,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }
