"""
Shared Neo4j knowledge-graph traversal.

Extracted from research_agent.py so the causal-chain query is callable
outside a FastAPI request context (specifically from backend/evaluation/
for the offline backtest harness).

Behavior is intentionally preserved: the Cypher query and the hardcoded
fallback are bit-for-bit identical to the originals in research_agent.py.
"""
import structlog

logger = structlog.get_logger()


# ── Single braces in Cypher — double braces were causing SyntaxError ──
KG_TRAVERSAL_QUERY = """
MATCH (e:Event)-[:CAUSES*1..3]->(impact)
WHERE e.name IN $entity_names OR e.type IN $signal_types
WITH impact, e
OPTIONAL MATCH (impact)-[:AFFECTS]->(sector:Sector {country: $country})
RETURN DISTINCT
  e.name as trigger,
  impact.name as effect,
  impact.type as effect_type,
  sector.name as india_sector,
  sector.sentiment as sector_sentiment,
  impact.avg_lag_days as lag_days,
  impact.strength as strength
ORDER BY impact.strength DESC
LIMIT 30
"""


async def query_knowledge_graph(
    neo4j_driver,
    entities: list,
    signal_types: list,
    country: str = "India",
) -> list:
    """Traverse the KG for causal chains originating from the given entities
    or signal types. Returns a list of dicts in the same shape the
    ResearchAgent has always consumed.

    Falls back to hand-authored chains if the driver is None or the query
    raises. This mirrors the prior ResearchAgent behavior exactly.
    """
    if not neo4j_driver:
        return _fallback_kg_data(entities, signal_types)

    try:
        async with neo4j_driver.session() as session:
            result = await session.run(
                KG_TRAVERSAL_QUERY,
                entity_names=entities[:10],
                signal_types=signal_types,
                country=country,
            )
            return await result.data()
    except Exception as e:
        logger.warning("kg_traversal.error", error=str(e))
        return _fallback_kg_data(entities, signal_types)


def _fallback_kg_data(entities: list, signal_types: list) -> list:
    """Hardcoded causal chains used when Neo4j is unavailable.
    Verbatim copy of the former ResearchAgent._get_fallback_kg_data.
    """
    base_connections = {
        "commodity": [
            {"trigger": "Oil Price Spike",    "effect": "Aviation Cost Rise",  "india_sector": "Aviation",    "sector_sentiment": "negative", "strength": 0.87},
            {"trigger": "Oil Price Spike",    "effect": "Paint Input Cost",    "india_sector": "Paints",      "sector_sentiment": "negative", "strength": 0.72},
            {"trigger": "Oil Price Spike",    "effect": "ONGC Revenue Boost",  "india_sector": "Oil & Gas",   "sector_sentiment": "positive", "strength": 0.91},
            {"trigger": "Oil Price Spike",    "effect": "CAD Widening",        "india_sector": "INR",         "sector_sentiment": "negative", "strength": 0.84},
        ],
        "geopolitical": [
            {"trigger": "War Risk",           "effect": "Gold Safe Haven",     "india_sector": "Gold",        "sector_sentiment": "positive", "strength": 0.78},
            {"trigger": "War Risk",           "effect": "FII Outflows",        "india_sector": "Equity",      "sector_sentiment": "negative", "strength": 0.65},
            {"trigger": "Supply Chain Shock", "effect": "Pharma Input Costs",  "india_sector": "Pharma",      "sector_sentiment": "negative", "strength": 0.55},
        ],
        "monetary": [
            {"trigger": "RBI Rate Hold",      "effect": "Banking NIM Stable",  "india_sector": "Banking",     "sector_sentiment": "neutral",  "strength": 0.70},
            {"trigger": "RBI Rate Cut",       "effect": "Real Estate Boost",   "india_sector": "Real Estate", "sector_sentiment": "positive", "strength": 0.80},
            {"trigger": "INR Depreciation",   "effect": "IT Revenue Boost",    "india_sector": "IT",          "sector_sentiment": "positive", "strength": 0.76},
        ],
        "trade": [
            {"trigger": "China Slowdown",     "effect": "Metal Demand Drop",   "india_sector": "Metals",      "sector_sentiment": "negative", "strength": 0.68},
            {"trigger": "Global Trade Drop",  "effect": "Export Sector Hurt",  "india_sector": "IT",          "sector_sentiment": "negative", "strength": 0.55},
        ],
    }

    connections: list = []
    for stype in signal_types:
        connections.extend(base_connections.get(stype, []))
    return connections if connections else base_connections["monetary"]
