"""
InvestAI Backend — FastAPI Application Entry Point
"""
import os
from dotenv import load_dotenv

# Load backend/.env if present. Codespaces secrets (already in process env)
# are NOT overridden because load_dotenv defaults to override=False.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import structlog

from database.connection import init_db, AsyncSessionLocal
from routes import auth, users, signals, portfolio, agents, subscriptions, alerts
from routes.whatif import router as whatif_router
from utils.scheduler import start_scheduler, stop_scheduler

logger = structlog.get_logger()


async def ensure_demo_user():
    """Seed demo_user so /api/agents/advice persists AdviceRecord + AdviceSignalLink.
    Without this seed, store_advice silently skips and the 24/7 thesis monitor
    has no rows to watch."""
    from sqlalchemy import select
    from models.models import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == "demo_user"))
        if result.scalar_one_or_none() is not None:
            return
        db.add(User(id="demo_user", email="demo@investai.local", name="Demo User"))
        try:
            await db.commit()
            logger.info("demo_user.seeded")
        except Exception as e:
            await db.rollback()
            logger.warning("demo_user.seed_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 InvestAI Backend starting...")
    await init_db()
    await ensure_demo_user()
    start_scheduler()
    logger.info("✅ All systems ready")
    yield
    logger.info("🛑 Shutting down...")
    stop_scheduler()


app = FastAPI(
    title="InvestAI API",
    description="AI-powered investment intelligence for Indian markets",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://192.168.99.100:3000",
        "https://investai.in",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/api/users",         tags=["Users"])
app.include_router(signals.router,       prefix="/api/signals",       tags=["Signals"])
app.include_router(portfolio.router,     prefix="/api/portfolio",     tags=["Portfolio"])
app.include_router(agents.router,        prefix="/api/agents",        tags=["Agents"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Subscriptions"])
app.include_router(alerts.router,        prefix="/api/alerts",        tags=["Alerts"])
app.include_router(whatif_router,        prefix="/api/whatif",        tags=["WhatIf"])


# ── Health Checks ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Liveness probe — process is alive."""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/health/ready")
async def readiness_check():
    """
    Readiness probe — every external dependency the API needs to serve a
    real request must be reachable. Returns 503 if any check fails so that
    a load balancer / Codespace devcontainer can keep traffic away while we
    boot.

    Checks:
      - Postgres: SELECT 1
      - Redis: PING (only if REDIS_URL is configured)

    Each component reports {ok: bool, error: str|None, latency_ms: int}.
    """
    import time
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    components: dict[str, dict] = {}

    # Postgres
    pg_start = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        components["postgres"] = {
            "ok": True,
            "latency_ms": int((time.perf_counter() - pg_start) * 1000),
            "error": None,
        }
    except Exception as e:
        components["postgres"] = {
            "ok": False,
            "latency_ms": int((time.perf_counter() - pg_start) * 1000),
            "error": str(e)[:200],
        }

    # Redis (only if configured)
    if os.getenv("REDIS_URL"):
        rd_start = time.perf_counter()
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(os.getenv("REDIS_URL"))
            try:
                pong = await r.ping()
            finally:
                await r.aclose()
            components["redis"] = {
                "ok": bool(pong),
                "latency_ms": int((time.perf_counter() - rd_start) * 1000),
                "error": None,
            }
        except Exception as e:
            components["redis"] = {
                "ok": False,
                "latency_ms": int((time.perf_counter() - rd_start) * 1000),
                "error": str(e)[:200],
            }
    else:
        components["redis"] = {"ok": True, "latency_ms": 0, "error": None, "skipped": True}

    overall_ok = all(c["ok"] for c in components.values())
    body = {
        "status": "ready" if overall_ok else "degraded",
        "components": components,
    }
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)