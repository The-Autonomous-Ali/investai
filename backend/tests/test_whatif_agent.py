"""Tests for WhatIfAgent — scenario simulation, LLM mocked."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from agents.whatif_agent import WhatIfAgent


@pytest.fixture
def agent():
    return WhatIfAgent(db_session=None, redis_client=None)


@pytest.fixture
def parse_response():
    """LLM response for the scenario-parser step."""
    return json.dumps({
        "scenario_title": "RBI cuts repo rate by 50bps",
        "scenario_type": "monetary",
        "probability": 0.3,
        "hypothetical_signal": {
            "title": "RBI rate cut 50bps",
            "signal_type": "monetary",
            "urgency": "breaking",
            "importance_score": 9.0,
            "confidence": 0.8,
            "geography": "india",
            "sentiment": "positive",
            "entities_mentioned": ["RBI", "Repo Rate"],
            "sectors_affected": {"banking": "negative", "real_estate": "positive"},
            "india_impact": "high",
            "chain_effects": ["Rate cut -> lower EMIs -> real estate demand rises"],
        },
        "parameter_changes": {
            "repo_rate_change": "-0.50%",
            "expected_nifty_move": "+1.5% to +2.5%",
            "expected_inr_move": "strengthens 0.3-0.5%",
            "expected_sectors_up": ["Real Estate", "Auto"],
            "expected_sectors_down": ["Banking (NIM compression)"],
            "bond_yield_change": "-20 to -30 bps",
        },
        "key_assumptions": ["Inflation is below 4%"],
        "what_invalidates_this": "US Fed raises rates simultaneously",
    })


@pytest.fixture
def impact_response():
    """LLM response for the impact-analysis step."""
    return json.dumps({
        "scenario_summary": "A 50bps RBI rate cut would boost real estate and auto sectors.",
        "baseline_vs_scenario": {
            "without_scenario": "Hold defensive positions",
            "with_scenario": "Shift to rate-sensitive sectors",
        },
        "portfolio_impact": {
            "positions_to_add": [
                {"instrument": "HDFC Bank", "reason": "Rate cut boosts recovery", "conviction": "medium"}
            ],
            "positions_to_reduce": [
                {"instrument": "Gold ETF", "reason": "Risk-on environment", "conviction": "low"}
            ],
            "positions_unchanged": [],
        },
        "new_allocation_suggestion": {
            "Real Estate Index Fund": {"percentage": 20, "reason": "Direct rate beneficiary"}
        },
        "timing_advice": "Buy before RBI announcement for maximum upside.",
        "probability_weighted_return": {
            "if_scenario_happens": "+8% in 3 months",
            "if_scenario_doesnt_happen": "+2% in 3 months",
            "probability_of_scenario": 0.3,
            "expected_value": "+3.8% expected",
        },
        "risk_factors": ["Global risk-off could negate domestic rate cut"],
        "monitoring_triggers": ["Watch CPI data for sub-4% print"],
        "action_checklist": ["Step 1: Monitor RBI MPC date", "Step 2: Position before announcement"],
    })


@pytest.mark.asyncio
async def test_simulate_returns_full_response(agent, parse_response, impact_response):
    """simulate() makes two LLM calls — parse then impact — and assembles the result."""
    with patch("agents.whatif_agent.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [parse_response, impact_response]
        result = await agent.simulate(
            scenario="What if RBI cuts rates by 50bps tomorrow?",
            current_portfolio={"equity": 70, "debt": 30},
            amount=500000,
            horizon="6 months",
            risk_profile="moderate",
        )

    assert result["scenario"] == "What if RBI cuts rates by 50bps tomorrow?"
    assert result["parsed_scenario"]["scenario_type"] == "monetary"
    assert result["impact_analysis"]["scenario_summary"] != ""
    assert "disclaimer" in result
    assert "generated_at" in result
    assert mock_llm.call_count == 2


@pytest.mark.asyncio
async def test_simulate_uses_default_args(agent, parse_response, impact_response):
    """simulate() works with only the required scenario argument."""
    with patch("agents.whatif_agent.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [parse_response, impact_response]
        result = await agent.simulate(scenario="What if Brent crude crosses $120?")

    assert "parsed_scenario" in result
    assert "impact_analysis" in result


@pytest.mark.asyncio
async def test_simulate_disclaimer_present(agent, parse_response, impact_response):
    """Result must always contain a SEBI-safe disclaimer."""
    with patch("agents.whatif_agent.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [parse_response, impact_response]
        result = await agent.simulate(scenario="What if India signs trade deal with China?")

    assert "SEBI" in result["disclaimer"]
    assert "hypothetical" in result["disclaimer"].lower()


@pytest.mark.asyncio
async def test_simulate_passes_market_snapshot(agent, parse_response, impact_response):
    """market_snapshot data should appear in the first LLM prompt."""
    snapshot = {"nifty50": 23500, "brent_crude": 95, "usd_inr": 83.5}
    with patch("agents.whatif_agent.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [parse_response, impact_response]
        await agent.simulate(
            scenario="What if oil crosses $120?",
            market_snapshot=snapshot,
        )

    first_call_prompt = mock_llm.call_args_list[0][0][0]
    # Snapshot values should be embedded in the first prompt
    assert "23500" in first_call_prompt or "nifty50" in first_call_prompt
