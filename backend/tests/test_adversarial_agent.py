"""Tests for AdversarialAgent — bull vs bear debate, LLM mocked."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from agents.adversarial_agent import AdversarialAgent


@pytest.fixture
def agent():
    return AdversarialAgent()


@pytest.fixture
def debate_response():
    return json.dumps({
        "bull_case": {
            "thesis": "Strong earnings growth ahead",
            "supporting_evidence": ["Revenue up 20%"],
            "catalysts": ["New product launch"],
            "strength": 7,
        },
        "bear_case": {
            "thesis": "Valuation stretched",
            "supporting_evidence": ["PE at 40x"],
            "risks": ["Margin compression"],
            "strength": 5,
        },
        "key_debate_point": "Can growth justify premium valuation?",
        "data_gaps": ["Insider trading data missing"],
        "factors_to_monitor": ["Quarterly results"],
    })


@pytest.mark.asyncio
async def test_debate_picks_returns_analyzed_picks(agent, debate_response):
    picks = [
        {"name": "Reliance Industries", "nse_symbol": "RELIANCE", "data_highlights": {}},
        {"name": "TCS", "nse_symbol": "TCS", "data_highlights": {}},
    ]
    with patch("agents.adversarial_agent.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = debate_response
        result = await agent.debate_picks(picks, {"risk_regime": "neutral"})

    assert len(result) == 2
    assert "debate" in result[0]
    assert result[0]["debate"]["bull_case"]["strength"] == 7
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_debate_picks_handles_llm_failure(agent):
    picks = [{"name": "FailCorp", "nse_symbol": "FAIL"}]
    with patch("agents.adversarial_agent.call_llm", new_callable=AsyncMock) as mock:
        mock.side_effect = Exception("LLM timeout")
        result = await agent.debate_picks(picks, {})

    assert result[0]["debate"]["bull_case"]["strength"] == 0
    assert "unavailable" in result[0]["debate"]["bull_case"]["thesis"].lower()


@pytest.mark.asyncio
async def test_debate_picks_empty_list(agent):
    result = await agent.debate_picks([], {})
    assert result == []
