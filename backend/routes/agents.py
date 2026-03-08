"""
/api/agents — Main investment advice endpoint
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database.connection import get_db
from agents.orchestrator import OrchestratorAgent
import redis.asyncio as aioredis
import os

router = APIRouter()


class AdviceRequest(BaseModel):
    query:   str   = Field(..., max_length=500)
    amount:  float = Field(..., gt=0, le=100_000_000)
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
    db:    Session = Depends(get_db),
    redis          = Depends(get_redis),
    # user_id would come from JWT auth in production
    # user: User = Depends(get_current_user),
):
    """
    Main advice endpoint. Runs the full multi-agent pipeline.
    Returns personalized investment recommendation.
    """
    user_id = "demo_user"  # replace with actual auth

    # Check subscription query limits
    # await check_query_limit(user_id, db)

    neo4j = get_neo4j()
    try:
        orchestrator = OrchestratorAgent(db, redis, neo4j)
        result = await orchestrator.run(
            user_id=user_id,
            query=request.query,
            amount=request.amount,
            horizon=request.horizon,
            country=request.country,
        )
        return AdviceResponse(**result)
    finally:
        await neo4j.close()


@router.get("/signals/current")
async def get_current_signals(
    db:    Session = Depends(get_db),
    redis          = Depends(get_redis),
):
    """Get current top market signals."""
    from agents.signal_watcher import SignalWatcherAgent
    agent  = SignalWatcherAgent(db, redis)
    result = await agent.get_current_signals()
    return result


@router.get("/signals/{signal_id}/timeline")
async def get_signal_timeline(
    signal_id: str,
    db: Session = Depends(get_db),
):
    """Get temporal lifecycle data for a specific signal."""
    from models.models import Signal
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return {
        "id":                   signal.id,
        "title":                signal.title,
        "stage":                signal.stage,
        "lifecycle_data":       signal.lifecycle_data,
        "probability_scenarios": signal.probability_scenarios,
        "early_warning_signals": signal.early_warning_signals,
        "resolution_conditions": signal.resolution_conditions,
    }


@router.get("/performance")
async def get_agent_performance(db: Session = Depends(get_db)):
    """Get performance metrics for all agents."""
    from models.models import AgentPerformance
    agents = db.query(AgentPerformance).all()
    return [{
        "agent_name":        a.agent_name,
        "accuracy_rate":     a.accuracy_rate,
        "total_runs":        a.total_runs,
        "avg_latency_ms":    a.avg_latency_ms,
        "signal_type_accuracy": a.signal_type_accuracy,
        "known_biases":      a.known_biases,
    } for a in agents]
