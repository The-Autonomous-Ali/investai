"""
What If Scenario API Route
Add this to your backend/routes/ folder as whatif.py
Then register it in main.py:
  from routes.whatif import router as whatif_router
  app.include_router(whatif_router)
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["WhatIf"])


class WhatIfRequest(BaseModel):
    scenario:          str
    amount:            float = 100000
    horizon:           str   = "1 year"
    risk_profile:      str   = "moderate"
    current_portfolio: Optional[dict] = None


@router.post("")
async def run_whatif_scenario(request: WhatIfRequest):
    """
    Run a What If scenario simulation.

    Example request:
    {
        "scenario": "What if RBI cuts interest rates by 50bps tomorrow?",
        "amount": 100000,
        "horizon": "1 year",
        "risk_profile": "moderate"
    }
    """
    from agents.whatif_agent import WhatIfAgent

    agent  = WhatIfAgent()
    result = await agent.simulate(
        scenario          = request.scenario,
        current_portfolio = request.current_portfolio,
        amount            = request.amount,
        horizon           = request.horizon,
        risk_profile      = request.risk_profile,
    )
    return result


@router.get("/examples")
async def get_scenario_examples():
    """Return example What If scenarios to show users."""
    return {
        "examples": [
            "What if RBI cuts interest rates by 50 basis points?",
            "What if Brent crude crosses $120 per barrel?",
            "What if India and Pakistan tensions escalate significantly?",
            "What if the US enters a recession in the next 6 months?",
            "What if India's GDP growth slows to 5%?",
            "What if China devalues the Yuan by 10%?",
            "What if the Fed cuts rates by 100bps this year?",
            "What if a major Indian bank faces an NPA crisis?",
            "What if India wins the semiconductor PLI scheme globally?",
            "What if monsoon fails this year — drought scenario?",
        ]
    }