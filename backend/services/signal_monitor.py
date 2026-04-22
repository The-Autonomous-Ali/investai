"""
Detect changes to the signals that originally drove prior advice.

This job does not issue investment instructions. It only tells the user when
the assumptions behind earlier analysis have materially changed.
"""

from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import AdviceRecord, AdviceSignalLink, EventStage, Signal, UserAlert

logger = structlog.get_logger()

IMPORTANCE_DROP_THRESHOLD = 2.0
TRACKED_STATUSES = ("active", "escalated")
WEAKENING_STAGES = {EventStage.DE_ESCALATING.value, EventStage.FADING.value}
RESOLVED_STAGES = {EventStage.RESOLVED.value}
ESCALATION_STAGES = {EventStage.ESCALATING.value}


def _stage_value(value) -> str:
    if isinstance(value, EventStage):
        return value.value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized.startswith("eventstage."):
            return normalized.split(".", 1)[1]
        return normalized
    return ""


async def check_signal_changes(db: AsyncSession) -> int:
    """Run the periodic thesis-change scan."""
    log = logger.bind(job="signal_monitor")
    log.info("signal_monitor.start")

    result = await db.execute(
        select(AdviceSignalLink).where(
            AdviceSignalLink.current_status.in_(TRACKED_STATUSES)
        )
    )
    tracked_links = result.scalars().all()

    if not tracked_links:
        log.info("signal_monitor.no_tracked_links")
        return 0

    signal_ids = [link.signal_id for link in tracked_links if link.signal_id]
    signals_by_id = {}
    if signal_ids:
        sig_result = await db.execute(select(Signal).where(Signal.id.in_(signal_ids)))
        for sig in sig_result.scalars().all():
            signals_by_id[sig.id] = sig

    alerts_created = 0
    for link in tracked_links:
        current_signal = signals_by_id.get(link.signal_id)
        change = _detect_change(link, current_signal)

        if not change:
            continue

        link.current_status = change["new_status"]
        link.change_detected_at = datetime.utcnow()
        link.change_description = change["description"]

        await _create_thesis_alert(db, link, change)
        alerts_created += 1

        log.info(
            "signal_monitor.change_detected",
            advice_id=link.advice_id,
            signal=link.signal_title,
            change=change["new_status"],
        )

    await db.commit()
    log.info("signal_monitor.complete", alerts_created=alerts_created)
    return alerts_created


def _detect_change(link: AdviceSignalLink, current_signal: Signal | None) -> dict | None:
    """Compare current signal state against the advice-time snapshot."""
    if current_signal is None:
        return {
            "new_status": "resolved",
            "description": f"Signal '{link.signal_title}' is no longer tracked by the system.",
            "severity": "info",
            "alert_title": f"Signal resolved: {link.signal_title}",
        }

    current_stage = _stage_value(current_signal.stage)
    snapshot_stage = _stage_value(link.stage_at_advice)

    if current_stage in RESOLVED_STAGES:
        return {
            "new_status": "resolved",
            "description": (
                f"Signal '{link.signal_title}' has been resolved. "
                f"Stage moved from '{snapshot_stage}' to '{current_stage}'. "
                f"The thesis behind your previous analysis may no longer apply."
            ),
            "severity": "warning",
            "alert_title": f"Signal resolved: {link.signal_title}",
        }

    if current_stage in WEAKENING_STAGES and snapshot_stage not in WEAKENING_STAGES:
        return {
            "new_status": "weakened",
            "description": (
                f"Signal '{link.signal_title}' is weakening. "
                f"Stage moved from '{snapshot_stage}' to '{current_stage}'. "
                f"The factors behind your previous analysis are losing strength."
            ),
            "severity": "warning",
            "alert_title": f"Signal weakening: {link.signal_title}",
        }

    if current_stage in ESCALATION_STAGES and snapshot_stage not in ESCALATION_STAGES:
        if link.current_status == "escalated":
            return None

        return {
            "new_status": "escalated",
            "description": (
                f"Signal '{link.signal_title}' has escalated. "
                f"Stage moved from '{snapshot_stage}' to '{current_stage}'. "
                f"The factors behind your previous analysis have intensified."
            ),
            "severity": "urgent",
            "alert_title": f"Signal escalating: {link.signal_title}",
        }

    if (
        link.importance_at_advice is not None
        and current_signal.importance_score is not None
    ):
        drop = link.importance_at_advice - current_signal.importance_score
        if drop >= IMPORTANCE_DROP_THRESHOLD:
            return {
                "new_status": "weakened",
                "description": (
                    f"Signal '{link.signal_title}' importance dropped from "
                    f"{link.importance_at_advice:.1f} to {current_signal.importance_score:.1f}. "
                    f"The market may be pricing this in or the situation is stabilizing."
                ),
                "severity": "info",
                "alert_title": f"Signal weakening: {link.signal_title}",
            }

    return None


async def _create_thesis_alert(
    db: AsyncSession,
    link: AdviceSignalLink,
    change: dict,
) -> None:
    """Create a UserAlert for the thesis change."""
    result = await db.execute(
        select(AdviceRecord.user_id).where(AdviceRecord.id == link.advice_id)
    )
    row = result.first()
    if not row:
        return

    user_id = row[0]
    alert = UserAlert(
        user_id=user_id,
        signal_id=link.signal_id,
        alert_type="thesis_change",
        title=change["alert_title"],
        message=change["description"],
        severity=change["severity"],
        is_read=False,
        action_required=(change["severity"] in ("warning", "urgent")),
    )
    db.add(alert)


async def create_signal_links_for_advice(
    db: AsyncSession,
    advice_id: str,
    signals: list[dict],
) -> None:
    """Snapshot the driving signals attached to a generated advice record."""
    for sig_dict in signals:
        link = AdviceSignalLink(
            advice_id=advice_id,
            signal_id=sig_dict.get("id"),
            signal_title=sig_dict.get("title", "Unknown signal"),
            signal_type=sig_dict.get("signal_type"),
            importance_at_advice=sig_dict.get("importance_score"),
            stage_at_advice=_stage_value(sig_dict.get("stage", "active")) or "active",
            sectors_affected=sig_dict.get("sectors_affected", {}),
            current_status="active",
        )
        db.add(link)

    await db.flush()
