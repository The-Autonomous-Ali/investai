from apscheduler.schedulers.background import BackgroundScheduler
import structlog

logger = structlog.get_logger()
scheduler = BackgroundScheduler()

def start_scheduler():
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