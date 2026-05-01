import pytest
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.orchestrator import OrchestratorAgent

@pytest.mark.asyncio
async def test_build_task_plan_does_not_call_llm():
    """Static plan must return without any LLM call."""
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    state = {
        "query": "should I buy Reliance",
        "amount": 100000,
        "horizon": "1 year",
        "country": "India",
        "user_profile": {},
    }
    plan = await orch._build_task_plan(state)
    assert "task_plan" in plan
    assert len(plan["task_plan"]) >= 9
    # investment_manager must NOT be in the plan
    agent_names = [t["agent"] for t in plan["task_plan"]]
    assert "investment_manager" not in agent_names

@pytest.mark.asyncio
async def test_static_plan_has_correct_dependencies():
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    state = {"query": "market outlook", "amount": 50000,
             "horizon": "6 months", "country": "India", "user_profile": {}}
    plan = await orch._build_task_plan(state)
    steps_by_num = {t["step"]: t for t in plan["task_plan"]}
    # global_macro must depend on signal_watcher (step 1)
    assert 1 in steps_by_num[2]["depends_on"]
    # research must depend on global_macro (step 2)
    assert 2 in steps_by_num[3]["depends_on"]
