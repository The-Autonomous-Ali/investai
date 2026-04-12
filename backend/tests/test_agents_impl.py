"""Tests for agents_impl — Portfolio, Tax, Critic, Temporal, Watchdog, PatternMatcher."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from agents.agents_impl import (
    PortfolioAgent, TaxAgent, CriticAgent,
    TemporalAgent, WatchdogAgent, PatternMatcherAgent,
)


# ── PortfolioAgent ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_portfolio_agent_run(mock_db_session):
    agent = PortfolioAgent(db_session=mock_db_session)
    llm_response = json.dumps({
        "sector_analysis": [{"sector": "IT", "signal_strength": "strong", "reasoning": "INR weak"}],
        "sectors_to_research": [],
        "sectors_showing_risk": [],
        "rebalancing_triggers": [],
        "general_principles": ["Diversify"],
        "narrative": "IT looks strong.",
        "analysis_confidence": 0.7,
        "review_date": "2026-07-01",
        "disclaimer": "Not investment advice.",
    })
    with patch("agents.agents_impl.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = llm_response
        result = await agent.run({"research_agent": {}, "country": "India"})

    assert result["analysis_confidence"] == 0.7
    assert "disclaimer" in result


# ── TaxAgent ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tax_agent_optimize():
    agent = TaxAgent()
    llm_response = json.dumps({
        "optimizations": [{"original": "Equity MF", "suggestion": "ELSS", "tax_benefit": "80C", "annual_saving_estimate": 15000}],
        "tax_advantaged_recommendation": {"amount": 150000, "benefit": "Save 46800"},
        "holding_period_advice": "Hold > 1 year for LTCG",
        "post_tax_return_estimate": "11% post-tax",
        "estimated_annual_tax_saving": 15000,
    })
    with patch("agents.agents_impl.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = llm_response
        result = await agent.optimize(
            portfolio={"allocation": {"equity": 70}},
            profile={"risk_tolerance": "moderate", "tax_bracket": 30},
            country="India",
        )

    assert result["estimated_annual_tax_saving"] == 15000


# ── CriticAgent ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_critic_agent_review():
    agent = CriticAgent()
    llm_response = json.dumps({
        "verdict": "REVISE",
        "overall_quality": 0.65,
        "risks": ["Concentration risk in IT"],
        "feedback": "Add diversification",
        "what_would_make_this_wrong": "Rupee strengthens unexpectedly",
        "suitability_check": "PASS",
        "suitability_notes": "",
    })
    with patch("agents.agents_impl.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = llm_response
        result = await agent.review({"portfolio": {}, "tax": {}, "signals": {"signals": []}})

    assert result["verdict"] == "REVISE"
    assert result["overall_quality"] == 0.65


# ── TemporalAgent ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_temporal_agent_assess_timelines(mock_db_session, sample_signals):
    agent = TemporalAgent(db_session=mock_db_session)
    llm_response = json.dumps({
        "timelines": [{
            "signal_title": "Fed holds rates steady",
            "duration_type": "medium_term",
            "lifecycle_stage": "developing",
            "estimated_duration_days": 60,
            "tomorrow_prediction": {"summary": "No change", "confidence": 0.8},
            "week_prediction": {"summary": "Watch CPI", "confidence": 0.6},
            "month_prediction": {"summary": "Rate cut possible", "confidence": 0.4},
            "resolution_conditions": ["CPI below 3%"],
            "escalation_signals": ["10Y above 4.5%"],
            "de_escalation_signals": ["CPI drops"],
            "probability_scenarios": {
                "best_case": {"desc": "Rate cut", "probability": 0.3, "timeline_days": 30},
                "base_case": {"desc": "Hold", "probability": 0.5, "timeline_days": 90},
                "worst_case": {"desc": "Hike", "probability": 0.2, "timeline_days": 60},
            },
            "resolution_cause": {"what_resolved_it": "", "source": "", "date": "", "confidence": 0.0},
        }],
        "recommended_review_date": "2026-06-01",
        "overall_market_phase": "cautious",
    })
    with patch("agents.agents_impl.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = llm_response
        result = await agent.assess_timelines(sample_signals)

    assert result["overall_market_phase"] == "cautious"
    assert len(result["timelines"]) == 1


@pytest.mark.asyncio
async def test_temporal_agent_empty_signals(mock_db_session):
    agent = TemporalAgent(db_session=mock_db_session)
    result = await agent.assess_timelines([])
    assert result["overall_market_phase"] == "neutral"
    assert result["timelines"] == []


# ── WatchdogAgent ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watchdog_detects_confidence_gap():
    agent = WatchdogAgent()
    outputs = {
        "research_agent": {"confidence_score": 0.9},
        "pattern_matcher": {"confidence_score": 0.3},
        "portfolio_agent": {},
    }
    conflicts = await agent.check(outputs)
    assert any(c["type"] == "CONFIDENCE_GAP" for c in conflicts)


@pytest.mark.asyncio
async def test_watchdog_detects_sector_conflict():
    agent = WatchdogAgent()
    outputs = {
        "research_agent": {
            "confidence_score": 0.7,
            "sectors_analysis": {"avoid": [{"sector": "Aviation"}]},
        },
        "pattern_matcher": {"confidence_score": 0.7},
        "portfolio_agent": {"sectors_to_buy": [{"sector": "Aviation"}]},
    }
    conflicts = await agent.check(outputs)
    assert any(c["type"] == "CONFLICT" for c in conflicts)


@pytest.mark.asyncio
async def test_watchdog_detects_hallucination():
    agent = WatchdogAgent()
    outputs = {
        "research_agent": {"confidence_score": 0.7},
        "pattern_matcher": {},
        "portfolio_agent": {"allocation": {"A" * 60: 50}},
    }
    conflicts = await agent.check(outputs)
    assert any(c["type"] == "HALLUCINATION_RISK" for c in conflicts)


@pytest.mark.asyncio
async def test_watchdog_no_conflicts():
    agent = WatchdogAgent()
    outputs = {
        "research_agent": {"confidence_score": 0.7, "sectors_analysis": {"avoid": []}},
        "pattern_matcher": {"confidence_score": 0.7},
        "portfolio_agent": {"sectors_to_buy": [], "allocation": {}},
    }
    conflicts = await agent.check(outputs)
    assert conflicts == []


# ── PatternMatcherAgent ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pattern_matcher_find_patterns(mock_db_session, sample_signals):
    agent = PatternMatcherAgent(db_session=mock_db_session)
    llm_response = json.dumps({
        "best_analogues": [{
            "year": 2022,
            "event": "Russia-Ukraine + Oil spike",
            "similarity_score": 78,
            "similarity_reasons": ["Oil above $90"],
            "what_happened": {"Energy": "+34%", "Aviation": "-22%"},
            "key_lesson": "Energy outperforms during commodity shocks",
        }],
        "pattern_quality": "medium",
        "confidence_score": 0.65,
        "caveat": "Current situation has different geopolitical dynamics",
    })
    with patch("agents.agents_impl.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = llm_response
        result = await agent.find_patterns(sample_signals)

    assert result["confidence_score"] == 0.65
    assert len(result["best_analogues"]) == 1


@pytest.mark.asyncio
async def test_pattern_matcher_empty_signals(mock_db_session):
    agent = PatternMatcherAgent(db_session=mock_db_session)
    result = await agent.find_patterns([])
    assert result["confidence_score"] == 0.3
    assert result["best_analogues"] == []
