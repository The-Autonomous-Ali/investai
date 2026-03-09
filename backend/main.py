"""
InvestAI Backend — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import structlog

from database.connection import init_db
from routes import auth, users, signals, portfolio, agents, subscriptions, alerts
from utils.scheduler import start_scheduler, stop_scheduler

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🚀 InvestAI Backend starting...")
    await init_db()
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

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://192.168.99.100:3000", "https://investai.in"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/api/users",         tags=["Users"])
app.include_router(signals.router,       prefix="/api/signals",       tags=["Signals"])
app.include_router(portfolio.router,     prefix="/api/portfolio",     tags=["Portfolio"])
app.include_router(agents.router,        prefix="/api/agents",        tags=["Agents"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Subscriptions"])
app.include_router(alerts.router,        prefix="/api/alerts",        tags=["Alerts"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}
