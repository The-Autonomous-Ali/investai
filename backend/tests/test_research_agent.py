"""Tests for ResearchAgent — LLM and Neo4j mocked."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.research_agent import ResearchAgent


@pytest.fixture
def research_response():
    return json.dumps({
        "top_signal": "Fed holds rates steady",
        "impact_chain": [
            {"step": 1, "cause": "Fed holds", "effect": "DXY strengthens", "confidence": 0.8}
        ],
        "country_specific_analysis": "India faces FII outflows.",
        "sectors_analysis": {
            "strong_buy": [],
            "buy": [{"sector": "IT", "reason": "INR depreciation helps", "instruments": ["TCS"]}],
            "neutral": [],
            "avoid": [{"sector": "Real Estate", "reason": "Rate premium", "risk_level": "high"}],
            "strong_avoid": [],
        },
        "currency_impact": "INR weakens to 83+",
        "inflation_impact": "Import inflation rises",
        "time_horizon": "medium_term",
        "root_cause_narrative": "Persistent US inflation forced the Fed to hold.",
        "key_assumptions": ["Fed stays hawkish through Q2"],
        "confidence_score": 0.75,
        "data_quality": "medium",
    })


@pytest.mark.asyncio
async def test_analyze_returns_parsed_response(mock_db_session, mock_neo4j_driver, sample_signals, research_response):
    agent = ResearchAgent(db_session=mock_db_session, neo4j_driver=mock_neo4j_driver)

    with patch("agents.research_agent.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("agents.research_agent.query_knowledge_graph", new_callable=AsyncMock) as mock_kg, \
         patch("agents.research_agent.query_root_cause_chain", new_callable=AsyncMock) as mock_rc:
        mock_llm.return_value = research_response
        mock_kg.return_value = []
        mock_rc.return_value = {"root_causes": []}

        result = await agent.analyze(sample_signals, country="India")

    assert result["top_signal"] == "Fed holds rates steady"
    assert result["confidence_score"] == 0.75
    assert len(result["sectors_analysis"]["buy"]) == 1


@pytest.mark.asyncio
async def test_analyze_empty_signals(mock_db_session, mock_neo4j_driver):
    agent = ResearchAgent(db_session=mock_db_session, neo4j_driver=mock_neo4j_driver)
    result = await agent.analyze([], country="India")
    assert result.get("error") == "no_signals"


@pytest.mark.asyncio
async def test_assemble_full_chain():
    signal_data = {"root_cause_chain": [{"event": "OPEC cut", "role": "root_cause"}]}
    research_result = {
        "impact_chain": [{"step": 1, "cause": "Oil spike", "effect": "Aviation down", "confidence": 0.8}],
        "root_cause_narrative": "OPEC cut production.",
    }
    temporal_data = {
        "timelines": [{
            "resolution_conditions": ["Ceasefire"],
            "resolution_cause": {"what_resolved_it": "", "source": "", "date": ""},
        }]
    }

    chain = ResearchAgent.assemble_full_chain(signal_data, research_result, temporal_data)
    assert len(chain["root_causes"]) == 1
    assert len(chain["forward_chain"]) == 1
    assert chain["root_cause_narrative"] == "OPEC cut production."
    assert "assembled_at" in chain
