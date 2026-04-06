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
from models.models import User, UserAlert, AdviceRecord, AdviceSignalLink
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


@router.get("/thesis-status")
async def get_thesis_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of all active analyses for this user.

    Shows whether the signals that drove each past analysis are still
    active, have weakened, reversed, or resolved.  This helps the user
    understand if a previous analysis is still relevant.
    """
    # Get user's recent advice records (last 10)
    advice_result = await db.execute(
        select(AdviceRecord)
        .where(AdviceRecord.user_id == user.id)
        .order_by(desc(AdviceRecord.created_at))
        .limit(10)
    )
    advice_records = advice_result.scalars().all()

    if not advice_records:
        return {"analyses": [], "summary": "No previous analyses found."}

    advice_ids = [a.id for a in advice_records]

    # Get all signal links for these advice records
    links_result = await db.execute(
        select(AdviceSignalLink)
        .where(AdviceSignalLink.advice_id.in_(advice_ids))
        .order_by(desc(AdviceSignalLink.created_at))
    )
    all_links = links_result.scalars().all()

    # Group links by advice_id
    links_by_advice = {}
    for link in all_links:
        links_by_advice.setdefault(link.advice_id, []).append(link)

    analyses = []
    needs_attention_count = 0

    for advice in advice_records:
        links = links_by_advice.get(advice.id, [])
        signal_statuses = []
        any_changed = False

        for link in links:
            status_entry = {
                "signal_title": link.signal_title,
                "signal_type":  link.signal_type,
                "status":       link.current_status,
                "importance_at_advice": link.importance_at_advice,
                "stage_at_advice":      link.stage_at_advice,
            }
            if link.change_detected_at:
                status_entry["change_detected_at"] = link.change_detected_at.isoformat()
                status_entry["change_description"] = link.change_description
                any_changed = True

            signal_statuses.append(status_entry)

        if any_changed:
            needs_attention_count += 1

        # Determine overall thesis health
        statuses = [l.current_status for l in links]
        if not links:
            thesis_health = "unknown"
        elif all(s == "active" for s in statuses):
            thesis_health = "still_valid"
        elif any(s == "reversed" for s in statuses):
            thesis_health = "outdated"
        elif any(s == "resolved" for s in statuses):
            thesis_health = "completed"
        elif any(s == "weakened" for s in statuses):
            thesis_health = "weakening"
        else:
            thesis_health = "still_valid"

        analyses.append({
            "advice_id":     advice.id,
            "query":         advice.user_query,
            "created_at":    advice.created_at.isoformat() if advice.created_at else None,
            "confidence":    advice.confidence_score,
            "thesis_health": thesis_health,
            "signals":       signal_statuses,
            "narrative":     (advice.narrative or "")[:300],
        })

    return {
        "analyses": analyses,
        "needs_attention": needs_attention_count,
        "summary": (
            f"You have {len(analyses)} recent analyses. "
            f"{needs_attention_count} need your attention because signals have changed."
            if needs_attention_count
            else f"You have {len(analyses)} recent analyses. All signals are still active."
        ),
    }


@router.get("/thesis-status/{advice_id}")
async def get_single_thesis_status(
    advice_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed thesis status for a single advice record."""
    # Verify this advice belongs to the user
    advice_result = await db.execute(
        select(AdviceRecord).where(
            AdviceRecord.id == advice_id,
            AdviceRecord.user_id == user.id,
        )
    )
    advice = advice_result.scalar_one_or_none()
    if not advice:
        raise HTTPException(status_code=404, detail="Analysis not found")

    links_result = await db.execute(
        select(AdviceSignalLink)
        .where(AdviceSignalLink.advice_id == advice_id)
    )
    links = links_result.scalars().all()

    signal_details = []
    for link in links:
        entry = {
            "signal_title":         link.signal_title,
            "signal_type":          link.signal_type,
            "status":               link.current_status,
            "importance_at_advice": link.importance_at_advice,
            "stage_at_advice":      link.stage_at_advice,
            "sectors_affected":     link.sectors_affected,
        }
        if link.change_detected_at:
            entry["change_detected_at"] = link.change_detected_at.isoformat()
            entry["change_description"] = link.change_description
        signal_details.append(entry)

    active_count = sum(1 for l in links if l.current_status == "active")
    changed_count = len(links) - active_count

    return {
        "advice_id":      advice.id,
        "query":          advice.user_query,
        "created_at":     advice.created_at.isoformat() if advice.created_at else None,
        "narrative":      advice.narrative,
        "confidence":     advice.confidence_score,
        "signals":        signal_details,
        "active_signals": active_count,
        "changed_signals": changed_count,
        "recommendation": (
            "All signals driving this analysis are still active."
            if changed_count == 0
            else f"{changed_count} of {len(links)} signals have changed. "
                 f"Consider reviewing this analysis with current data."
        ),
        "disclaimer": (
            "This is a factual status update about market signals, not investment advice. "
            "Review the current data and make your own decisions."
        ),
    }


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
