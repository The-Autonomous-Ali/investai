"""
/api/agents — Main investment advice endpoint
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.connection import get_db
from agents.agents_impl import MemoryAgent
from agents.orchestrator import OrchestratorAgent
from models.models import User
from services.entitlements import consume_advice_quota, ensure_advice_quota
from services.rate_limiter import enforce_ip_limit, enforce_user_limit
from services.recommendation_policy import RecommendationPolicy
from utils.auth import get_current_user
import redis.asyncio as aioredis
import os


def _client_ip(http_request: Request) -> str:
    forwarded = http_request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"

router = APIRouter()


class AdviceRequest(BaseModel):
    query:   str   = Field(..., max_length=500)
    amount:  float = Field(default=0, ge=0, le=100_000_000)
    horizon: str   = Field(default="1 year")
    country: str   = Field(default="India")


class AdviceResponse(BaseModel):
    success: bool
    recommendation: dict | None = None
    meta:           dict | None = None
    error:          str  | None = None


async def get_redis():
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    try:
        yield r
    finally:
        await r.close()


def get_neo4j():
    from neo4j import AsyncGraphDatabase
    url      = os.getenv("NEO4J_URL",      "bolt://localhost:7687")
    user     = os.getenv("NEO4J_USER",     "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "investai123")
    return AsyncGraphDatabase.driver(url, auth=(user, password))


@router.post("/advice", response_model=AdviceResponse)
async def get_investment_advice(
    request: AdviceRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db:    AsyncSession = Depends(get_db),  # FIX: was Session (sync), now AsyncSession
    redis              = Depends(get_redis),
):
    """
    Main advice endpoint. Runs the full multi-agent pipeline.
    Returns personalized investment recommendation.
    """
    await enforce_ip_limit(redis, _client_ip(http_request))
    await enforce_user_limit(redis, user.id)
    ensure_advice_quota(user)
    neo4j = get_neo4j()
    try:
        orchestrator = OrchestratorAgent(db, redis, neo4j)
        result = await orchestrator.run(
            user_id=user.id,
            query=request.query,
            amount=request.amount,
            horizon=request.horizon,
            country=request.country,
        )
        if result.get("success") and result.get("recommendation"):
            memory = MemoryAgent(db)
            user_context = await memory.get_user_context(user.id)
            policy = RecommendationPolicy()
            result["recommendation"] = policy.build(
                query=request.query,
                amount=request.amount,
                horizon=request.horizon,
                country=request.country,
                user_profile=user_context,
                analysis=result["recommendation"],
            )
            result.setdefault("meta", {})
            result["meta"]["policy_version"] = result["recommendation"]["policy_version"]
            result["meta"]["usage"] = consume_advice_quota(user)
            await db.commit()
        return AdviceResponse(**result)
    finally:
        await neo4j.close()


@router.get("/signals/current")
async def get_current_signals(
    db:    AsyncSession = Depends(get_db),  # FIX: was Session
    redis              = Depends(get_redis),
):
    """Get current top market signals."""
    from agents.signal_watcher import SignalWatcherAgent
    agent  = SignalWatcherAgent(db, redis)
    result = await agent.get_current_signals()
    return result


@router.get("/signals/{signal_id}/timeline")
async def get_signal_timeline(
    signal_id: str,
    db: AsyncSession = Depends(get_db),  # FIX: was Session
):
    """Get temporal lifecycle data for a specific signal."""
    from models.models import Signal

    # FIX: was db.query(Signal).filter(...).first()
    # db.query() does not exist on AsyncSession — crashes at runtime
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return {
        "id":                    signal.id,
        "title":                 signal.title,
        "stage":                 signal.stage,
        "lifecycle_data":        signal.lifecycle_data,
        "probability_scenarios": signal.probability_scenarios,
        "early_warning_signals": signal.early_warning_signals,
        "resolution_conditions": signal.resolution_conditions,
    }


@router.get("/performance")
async def get_agent_performance(db: AsyncSession = Depends(get_db)):  # FIX: was Session
    """Get performance metrics for all agents."""
    from models.models import AgentPerformance

    # FIX: was db.query(AgentPerformance).all()
    # Same bug — .query() doesn't exist on AsyncSession
    result = await db.execute(select(AgentPerformance))
    agents = result.scalars().all()

    return [{
        "agent_name":           a.agent_name,
        "accuracy_rate":        a.accuracy_rate,
        "total_runs":           a.total_runs,
        "avg_latency_ms":       a.avg_latency_ms,
        "signal_type_accuracy": a.signal_type_accuracy,
        "known_biases":         a.known_biases,
    } for a in agents]
