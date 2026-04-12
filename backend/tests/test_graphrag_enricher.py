"""Tests for GraphRAGEnricher — LLM and Neo4j mocked."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.graphrag_enricher import GraphRAGEnricher


@pytest.fixture
def enricher(mock_neo4j_driver):
    return GraphRAGEnricher(neo4j_driver=mock_neo4j_driver)


@pytest.fixture
def extraction_response():
    return json.dumps({
        "entities": [
            {"name": "Oil Price Spike", "type": "Event", "properties": {"event_type": "commodity"}},
            {"name": "Aviation", "type": "Sector", "properties": {"country": "India"}},
        ],
        "relationships": [
            {
                "from": "Oil Price Spike", "from_type": "Event",
                "relationship": "AFFECTS",
                "to": "Aviation", "to_type": "Sector",
                "properties": {"sentiment": "negative", "strength": 0.87},
            }
        ],
        "india_relevance_score": 0.85,
        "key_insight": "Oil spike hurts Indian aviation margins",
    })


@pytest.mark.asyncio
async def test_enrich_from_article_success(enricher, extraction_response):
    with patch("agents.graphrag_enricher.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = extraction_response
        result = await enricher.enrich_from_article(
            article_text="Oil prices surged past $95 as OPEC announced further production cuts.",
            source="Reuters Business",
        )

    assert result["enriched"] is True
    assert result["entities_extracted"] == 2
    assert result["relationships_found"] == 1
    assert result["india_relevance"] == 0.85


@pytest.mark.asyncio
async def test_enrich_skips_short_article(enricher):
    result = await enricher.enrich_from_article(article_text="Short", source="test")
    assert result["enriched"] is False
    assert result["reason"] == "article_too_short"


@pytest.mark.asyncio
async def test_enrich_skips_low_relevance(enricher):
    low_relevance = json.dumps({"india_relevance_score": 0.1, "entities": [], "relationships": []})
    with patch("agents.graphrag_enricher.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = low_relevance
        result = await enricher.enrich_from_article(
            article_text="European weather forecast shows mild winter ahead for Germany.",
            source="BBC",
        )

    assert result["enriched"] is False
    assert result["reason"] == "low_india_relevance"


@pytest.mark.asyncio
async def test_enrich_without_neo4j():
    enricher = GraphRAGEnricher(neo4j_driver=None)
    response = json.dumps({
        "entities": [{"name": "Test", "type": "Event", "properties": {}}],
        "relationships": [],
        "india_relevance_score": 0.8,
        "key_insight": "Test",
    })
    with patch("agents.graphrag_enricher.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = response
        result = await enricher.enrich_from_article(
            article_text="A sufficiently long article about Indian market impact from global events.",
            source="Test",
        )

    assert result["enriched"] is True
    assert result["neo4j_result"]["neo4j"] == "unavailable"
