"""
Signal Monitor — Detects when signals that drove previous advice have changed.

This is the "weather changed" detector.  It does NOT tell users to buy or sell.
It tells them: "The signal behind your previous analysis has shifted — here's
what the data shows now, you decide what to do."

Runs as a periodic worker job (every 30 minutes).

Flow:
1. Load all AdviceSignalLink rows with current_status='active'
2. For each, fetch the current Signal from DB
3. Compare current state vs snapshot (stage change, importance shift, resolution)
4. If significant change detected → update AdviceSignalLink + create UserAlert
"""
import structlog
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import (
    AdviceSignalLink, AdviceRecord, Signal, UserAlert, EventStage,
)

logger = structlog.get_logger()

# ─── Change detection thresholds ─────────────────────────────────────────────

# If importance score dropped by this much, flag as weakened
IMPORTANCE_DROP_THRESHOLD = 2.0

# Stage transitions that mean "the signal weakened or reversed"
WEAKENING_STAGES = {EventStage.DE_ESCALATING, EventStage.FADING}
RESOLVED_STAGES  = {EventStage.RESOLVED}

# Stage transitions that mean "the signal escalated"
ESCALATION_STAGES = {EventStage.ESCALATING}


async def check_signal_changes(db: AsyncSession) -> int:
    """Main entry point — called by the worker every 30 minutes.

    Returns the number of alerts created.
    """
    log = logger.bind(job="signal_monitor")
    log.info("signal_monitor.start")

    # 1. Get all active links (signals that haven't changed yet)
    result = await db.execute(
        select(AdviceSignalLink)
        .where(AdviceSignalLink.current_status == "active")
    )
    active_links = result.scalars().all()

    if not active_links:
        log.info("signal_monitor.no_active_links")
        return 0

    # 2. Batch-fetch all referenced signals
    signal_ids = [link.signal_id for link in active_links if link.signal_id]
    signals_by_id = {}
    if signal_ids:
        sig_result = await db.execute(
            select(Signal).where(Signal.id.in_(signal_ids))
        )
        for sig in sig_result.scalars().all():
            signals_by_id[sig.id] = sig

    # 3. Check each link for changes
    alerts_created = 0
    for link in active_links:
        current_signal = signals_by_id.get(link.signal_id)
        change = _detect_change(link, current_signal)

        if change:
            link.current_status = change["new_status"]
            link.change_detected_at = datetime.utcnow()
            link.change_description = change["description"]

            # Create alert for the user
            await _create_thesis_alert(db, link, change)
            alerts_created += 1

            log.info("signal_monitor.change_detected",
                     advice_id=link.advice_id,
                     signal=link.signal_title,
                     change=change["new_status"])

    await db.commit()
    log.info("signal_monitor.complete", alerts_created=alerts_created)
    return alerts_created


def _detect_change(link: AdviceSignalLink, current_signal: Signal | None) -> dict | None:
    """Compare current signal state against the advice-time snapshot.

    Returns a change dict or None if no significant change.
    """
    # Signal was deleted or not found — treat as resolved
    if current_signal is None:
        return {
            "new_status": "resolved",
            "description": f"Signal '{link.signal_title}' is no longer tracked by the system.",
            "severity": "info",
            "alert_title": f"Signal resolved: {link.signal_title}",
        }

    current_stage = current_signal.stage
    snapshot_stage = link.stage_at_advice

    # ── Check for resolution ──────────────────────────────────────────────
    if current_stage in RESOLVED_STAGES:
        return {
            "new_status": "resolved",
            "description": (
                f"Signal '{link.signal_title}' has been resolved. "
                f"Stage moved from '{snapshot_stage}' to '{current_stage.value}'. "
                f"The thesis behind your previous analysis may no longer apply."
            ),
            "severity": "warning",
            "alert_title": f"Signal resolved: {link.signal_title}",
        }

    # ── Check for weakening / de-escalation ───────────────────────────────
    if current_stage in WEAKENING_STAGES and snapshot_stage not in (
        EventStage.DE_ESCALATING.value, EventStage.FADING.value
    ):
        return {
            "new_status": "weakened",
            "description": (
                f"Signal '{link.signal_title}' is weakening. "
                f"Stage moved from '{snapshot_stage}' to '{current_stage.value}'. "
                f"The factors behind your previous analysis are losing strength."
            ),
            "severity": "warning",
            "alert_title": f"Signal weakening: {link.signal_title}",
        }

    # ── Check for escalation ──────────────────────────────────────────────
    if current_stage in ESCALATION_STAGES and snapshot_stage not in (
        EventStage.ESCALATING.value,
    ):
        return {
            "new_status": "active",  # stays active but we alert
            "description": (
                f"Signal '{link.signal_title}' has escalated. "
                f"Stage moved from '{snapshot_stage}' to '{current_stage.value}'. "
                f"The factors behind your previous analysis have intensified."
            ),
            "severity": "urgent",
            "alert_title": f"Signal escalating: {link.signal_title}",
        }

    # ── Check for significant importance drop ─────────────────────────────
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
                    f"The market may be pricing this in or the situation is stabilising."
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
    # Find the user from the advice record
    result = await db.execute(
        select(AdviceRecord.user_id)
        .where(AdviceRecord.id == link.advice_id)
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
    """Called after advice is generated to snapshot the driving signals.

    ``signals`` is the list of signal dicts from the orchestrator
    (same shape as what signal_watcher returns).
    """
    for sig_dict in signals:
        link = AdviceSignalLink(
            advice_id=advice_id,
            signal_id=sig_dict.get("id"),
            signal_title=sig_dict.get("title", "Unknown signal"),
            signal_type=sig_dict.get("signal_type"),
            importance_at_advice=sig_dict.get("importance_score"),
            stage_at_advice=sig_dict.get("stage", "active"),
            sectors_affected=sig_dict.get("sectors_affected", {}),
            current_status="active",
        )
        db.add(link)

    await db.flush()  # don't commit — let the caller commit
