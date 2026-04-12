"""Tests for GlobalMacroAgent — all LLM calls mocked."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from agents.global_macro_agent import GlobalMacroAgent


@pytest.fixture
def agent():
    return GlobalMacroAgent(db_session=None, redis_client=None)


@pytest.fixture
def macro_llm_response():
    return json.dumps({
        "global_risk_score": 7,
        "risk_regime": "risk_off",
        "primary_global_theme": "Fed hawkishness + strong dollar",
        "india_impact_summary": "FII outflows likely as US yields rise.",
        "signal_scores": [
            {
                "signal_title": "Fed holds rates steady",
                "india_impact_score": 8.0,
                "transmission_mechanism": "DXY up -> FII sell -> Nifty down",
                "affected_india_sectors": {"it": "positive", "banking": "negative"},
                "key_variable_to_watch": "US 10Y above 4.5%",
                "time_horizon": "1-3 months",
            }
        ],
        "macro_tailwinds_for_india": ["China slowdown -> India gains"],
        "macro_headwinds_for_india": ["Strong dollar -> FII outflows"],
        "watch_list": [],
        "pre_market_brief": "Caution advised before NSE open.",
    })


@pytest.mark.asyncio
async def test_analyze_returns_parsed_llm_response(agent, sample_signals, macro_llm_response):
    with patch("agents.global_macro_agent.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = macro_llm_response
        result = await agent.analyze(sample_signals, {})

    assert result["global_risk_score"] == 7
    assert result["risk_regime"] == "risk_off"
    assert len(result["signal_scores"]) == 1
    mock.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_empty_signals_returns_neutral(agent):
    result = await agent.analyze([], {})
    assert result["global_risk_score"] == 5
    assert result["risk_regime"] == "neutral"


@pytest.mark.asyncio
async def test_analyze_filters_global_signals(agent, macro_llm_response):
    signals = [
        {"title": "RBI holds rate", "geography": "india"},
        {"title": "Fed hikes", "geography": "us"},
    ]
    with patch("agents.global_macro_agent.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = macro_llm_response
        await agent.analyze(signals, {})

    call_args = mock.call_args[0][0]
    assert "Fed hikes" in call_args


@pytest.mark.asyncio
async def test_get_pre_market_brief(agent, sample_signals, macro_llm_response):
    with patch("agents.global_macro_agent.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = macro_llm_response
        brief = await agent.get_pre_market_brief(sample_signals, {})

    assert "Caution" in brief
