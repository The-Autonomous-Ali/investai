"""
utils/scheduler.py

NOTE: Scheduled jobs (signal scanning, advice scoring) run in the
dedicated `worker` Docker service (backend/worker.py).
This scheduler is a stub kept for future in-process lightweight tasks.
"""
from apscheduler.schedulers.background import BackgroundScheduler
import structlog

logger = structlog.get_logger()
scheduler = BackgroundScheduler()


def start_scheduler():
    # No jobs here — see backend/worker.py for the job definitions
    try:
        scheduler.start()
        logger.info("✅ Scheduler started")
    except Exception as e:
        logger.error(f"❌ Scheduler failed to start: {e}")


def stop_scheduler():
    try:
        scheduler.shutdown()
        logger.info("🛑 Scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Scheduler failed to stop: {e}")