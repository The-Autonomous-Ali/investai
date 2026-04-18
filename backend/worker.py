"""
Background Worker — Runs scheduled tasks:
- Every 15 min: Scan all signal sources (legacy path + new ingestion dispatcher)
- Continuously: signal_extractor consumer drains the signals.raw stream
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

# Handle to the continuously-running signal extractor. Set in main().
_extractor_task: asyncio.Task | None = None
_extractor_instance = None


async def scan_signals():
    """Scan all signal sources and store new signals.

    Now wires in the Neo4j driver so SignalWatcherAgent can enrich the
    knowledge graph (RootCause/Event/Sector nodes + CAUSES/AFFECTS edges)
    for every new signal ingested.
    """
    logger.info("worker.scan_signals.start")
    try:
        from database.connection import AsyncSessionLocal
        from agents.signal_watcher import SignalWatcherAgent
        import redis.asyncio as aioredis
        import os

        redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

        # Neo4j driver — shared across all feeds in this run. If connection
        # fails we fall back to a None driver so Postgres ingestion still
        # works and the enricher silently no-ops.
        neo4j_driver = None
        try:
            from neo4j import AsyncGraphDatabase
            neo4j_driver = AsyncGraphDatabase.driver(
                os.getenv("NEO4J_URL", "bolt://localhost:7687"),
                auth=(
                    os.getenv("NEO4J_USER", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", "investai123"),
                ),
            )
        except Exception as e:
            logger.warning("worker.neo4j_init_failed", error=str(e))

        try:
            async with AsyncSessionLocal() as db:
                agent   = SignalWatcherAgent(db, redis, neo4j_driver=neo4j_driver)
                signals = await agent.scan_all_sources()
                logger.info("worker.scan_signals.complete", new_signals=len(signals))
        finally:
            if neo4j_driver is not None:
                try:
                    await neo4j_driver.close()
                except Exception as e:
                    logger.warning("worker.neo4j_close_failed", error=str(e))
            await redis.close()
    except Exception as e:
        logger.error("worker.scan_signals.error", error=str(e))


async def run_ingestion_dispatcher():
    """Iterate every connector in feed_registry and call .run() on each.

    This is the new pipeline — connectors push RawSignals onto the
    signals.raw Redis Stream, and the continuously-running extractor
    task drains the stream into the Postgres signals table.

    Each connector isolates its own failures via BaseConnector.run(),
    so one broken feed cannot kill the batch.
    """
    logger.info("worker.ingestion_dispatcher.start")
    try:
        from ingestion.feed_registry import get_all_connectors
        connectors = get_all_connectors()

        # Run connectors concurrently — most of their wall time is I/O.
        # gather(return_exceptions=True) so one crash doesn't cancel peers.
        results = await asyncio.gather(
            *[c.run() for c in connectors],
            return_exceptions=True,
        )
        total_new = sum(r for r in results if isinstance(r, int))
        errors = sum(1 for r in results if isinstance(r, Exception))
        logger.info(
            "worker.ingestion_dispatcher.complete",
            connectors=len(connectors),
            new_signals=total_new,
            errors=errors,
        )
    except Exception as e:
        logger.error("worker.ingestion_dispatcher.error", error=str(e))


async def run_signal_extractor_loop():
    """Long-running consumer — drains signals.raw into the Signal table.

    Started once at worker boot and runs until worker shuts down.
    Survives Redis/LLM outages via internal try/except in the extractor.
    """
    global _extractor_instance
    try:
        from ingestion.signal_extractor import SignalExtractor
        _extractor_instance = SignalExtractor()
        logger.info(
            "worker.signal_extractor.starting",
            consumer=_extractor_instance.consumer_name,
        )
        await _extractor_instance.run_forever()
    except asyncio.CancelledError:
        logger.info("worker.signal_extractor.cancelled")
        raise
    except Exception as e:
        logger.error("worker.signal_extractor.crashed", error=str(e))


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
    scheduler.add_job(scan_signals,             IntervalTrigger(minutes=15),            id="scan_signals",         replace_existing=True)
    scheduler.add_job(run_ingestion_dispatcher, IntervalTrigger(minutes=15),            id="ingestion_dispatcher", replace_existing=True)
    scheduler.add_job(monitor_signal_changes,   IntervalTrigger(minutes=30),            id="signal_monitor",       replace_existing=True)
    scheduler.add_job(update_event_lifecycles,  CronTrigger(hour=6, minute=0),          id="lifecycle",            replace_existing=True)
    scheduler.add_job(score_advice_performance, CronTrigger(day_of_week='sun', hour=2), id="score_advice",         replace_existing=True)
    scheduler.start()
    logger.info(
        "worker.scheduler.started",
        jobs=[
            "scan_signals(15m)",
            "ingestion_dispatcher(15m)",
            "signal_monitor(30m)",
            "lifecycle(6am)",
            "score_advice(sun)",
        ],
    )


def stop_scheduler():
    scheduler.shutdown()


async def main():
    global _extractor_task
    logger.info("Starting background worker...")
    start_scheduler()

    # Kick off the continuous stream consumer alongside the scheduler.
    _extractor_task = asyncio.create_task(run_signal_extractor_loop())

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler()
        if _extractor_instance is not None:
            _extractor_instance.stop()
        if _extractor_task is not None:
            _extractor_task.cancel()
            try:
                await _extractor_task
            except (asyncio.CancelledError, Exception):
                pass


if __name__ == "__main__":
    asyncio.run(main())