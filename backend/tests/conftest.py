"""Shared test fixtures — mock LLM, mock DB session, mock Neo4j driver."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_llm():
    """Patch call_llm globally. Set .return_value to control LLM output per test."""
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = "{}"
        yield mock


@pytest.fixture
def mock_db_session():
    """Async DB session stub. Override .execute().scalars().all() per test."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    result = AsyncMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.fixture
def mock_neo4j_driver():
    """Neo4j driver stub. Returns empty results by default."""
    driver = AsyncMock()
    neo4j_session = AsyncMock()
    neo4j_session.run = AsyncMock(return_value=AsyncMock(data=AsyncMock(return_value=[])))
    driver.session = MagicMock(return_value=neo4j_session)
    # Support async context manager: async with driver.session() as s
    neo4j_session.__aenter__ = AsyncMock(return_value=neo4j_session)
    neo4j_session.__aexit__ = AsyncMock(return_value=False)
    return driver


@pytest.fixture
def sample_signals():
    """Realistic signal list for agent tests."""
    return [
        {
            "id": 1,
            "title": "Fed holds rates steady at 5.25-5.50%",
            "signal_type": "monetary",
            "urgency": "breaking",
            "importance_score": 8.5,
            "confidence": 0.9,
            "geography": "us",
            "sentiment": "neutral",
            "entities_mentioned": ["Fed", "US Treasury"],
            "sectors_affected": {"banking": "positive", "real_estate": "negative"},
            "root_cause_chain": [
                {"event": "Persistent inflation above 3%", "role": "root_cause", "source": "BLS", "date": "2026-03-15"}
            ],
        },
        {
            "id": 2,
            "title": "Brent crude surges past $95 on OPEC cuts",
            "signal_type": "commodity",
            "urgency": "developing",
            "importance_score": 7.8,
            "confidence": 0.85,
            "geography": "global",
            "sentiment": "negative",
            "entities_mentioned": ["OPEC", "Brent Crude", "Saudi Arabia"],
            "sectors_affected": {"aviation": "negative", "energy": "positive", "paint": "negative"},
        },
    ]
