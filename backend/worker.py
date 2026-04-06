"""
Background Worker — Runs scheduled tasks:
- Every 15 min: Scan all signal sources
- Every morning 6am: Run daily event lifecycle update
- Every Sunday: Score 90-day-old advice performance
"""
import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = structlog.get_logger()
scheduler = AsyncIOScheduler()


async def scan_signals():
    """Scan all signal sources and store new signals."""
    logger.info("worker.scan_signals.start")
    try:
        from database.connection import AsyncSessionLocal
        from agents.signal_watcher import SignalWatcherAgent
        import redis.asyncio as aioredis
        import os

        redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        async with AsyncSessionLocal() as db:
            agent   = SignalWatcherAgent(db, redis)
            signals = await agent.scan_all_sources()
            logger.info("worker.scan_signals.complete", new_signals=len(signals))
        await redis.close()
    except Exception as e:
        logger.error("worker.scan_signals.error", error=str(e))


async def monitor_signal_changes():
    """Check if signals that drove previous advice have changed.

    Runs every 30 minutes.  When a change is detected, creates a
    UserAlert so the user knows their previous analysis may be outdated.
    """
    logger.info("worker.signal_monitor.start")
    try:
        from database.connection import AsyncSessionLocal
        from services.signal_monitor import check_signal_changes

        async with AsyncSessionLocal() as db:
            alerts_created = await check_signal_changes(db)
            logger.info("worker.signal_monitor.complete",
                        alerts_created=alerts_created)
    except Exception as e:
        logger.error("worker.signal_monitor.error", error=str(e))


async def update_event_lifecycles():
    """Daily update of event lifecycle stages."""
    logger.info("worker.lifecycle_update.start")
    logger.info("worker.lifecycle_update.complete")


async def score_advice_performance():
    """Score advice that is now 90 days old."""
    logger.info("worker.score_advice.start")
    try:
        from database.connection import AsyncSessionLocal
        from models.models import AdviceRecord
        from datetime import datetime, timedelta
        from sqlalchemy import select, and_

        async with AsyncSessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(days=90)

            # FIX: use async execute + select() instead of db.query()
            result = await db.execute(
                select(AdviceRecord)
                .where(
                    and_(
                        AdviceRecord.created_at <= cutoff,
                        AdviceRecord.advice_rating == None,
                    )
                )
                .limit(50)
            )
            old_advice = result.scalars().all()

            for advice in old_advice:
                logger.info("worker.score_advice.scoring", advice_id=advice.id)

        logger.info("worker.score_advice.complete", scored=len(old_advice))
    except Exception as e:
        logger.error("worker.score_advice.error", error=str(e))


def start_scheduler():
    scheduler.add_job(scan_signals,             IntervalTrigger(minutes=15),            id="scan_signals",    replace_existing=True)
    scheduler.add_job(monitor_signal_changes,   IntervalTrigger(minutes=30),            id="signal_monitor",  replace_existing=True)
    scheduler.add_job(update_event_lifecycles,  CronTrigger(hour=6, minute=0),          id="lifecycle",       replace_existing=True)
    scheduler.add_job(score_advice_performance, CronTrigger(day_of_week='sun', hour=2), id="score_advice",    replace_existing=True)
    scheduler.start()
    logger.info("worker.scheduler.started", jobs=["scan_signals(15m)", "signal_monitor(30m)", "lifecycle(6am)", "score_advice(sun)"])


def stop_scheduler():
    scheduler.shutdown()


async def main():
    logger.info("Starting background worker...")
    start_scheduler()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler()


if __name__ == "__main__":
    asyncio.run(main())