"""Backtest-specific Neo4j traversal.

Unlike the shared `agents.kg_traversal.query_knowledge_graph` helper
(which preserves the legacy query shape used by ResearchAgent), this
module pulls the `direction` property off the CAUSES relationship, which
is what the seed graph actually stores and what the backtest needs.

Falls back to the shared fallback data if Neo4j is unavailable so unit
tests and local dev still work without a running graph.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from agents.kg_traversal import _fallback_kg_data

logger = structlog.get_logger()


# Traversal that returns the edge direction (not the node sentiment).
# One-hop only: from the seed Event to a Sector, with at most one
# intermediate Event on the path to handle chains like
#   Middle East Conflict -> Oil Price Spike -> Aviation.
KG_EDGE_QUERY = """
MATCH (e:Event)-[:CAUSES*1..3]->(s:Sector {country: $country})
WHERE e.name = $event_name OR e.type = $signal_type
MATCH p = (e)-[:CAUSES*1..3]->(s)
WITH e, s, relationships(p) AS rels
WITH e, s, [r IN rels WHERE type(r) = 'CAUSES' AND r.direction IS NOT NULL][-1] AS final_rel
WHERE final_rel IS NOT NULL
RETURN DISTINCT
  e.name       AS event_name,
  s.name       AS sector,
  final_rel.direction    AS direction,
  final_rel.strength     AS strength,
  final_rel.avg_lag_days AS lag_days
"""


@dataclass(frozen=True)
class KGPrediction:
    event_name: str
    sector: str
    direction: str      # positive | negative | neutral
    strength: float
    lag_days: int | None


def _normalize_direction(raw) -> str:
    """Collapse the various shapes the graph uses into canonical values."""
    if raw is None:
        return "neutral"
    s = str(raw).strip().lower()
    if s in ("positive", "pos", "up", "+", "bullish"):
        return "positive"
    if s in ("negative", "neg", "down", "-", "bearish"):
        return "negative"
    return "neutral"


async def query_kg_for_event(
    neo4j_driver,
    event_name: str,
    signal_type: str,
    country: str = "India",
) -> list[KGPrediction]:
    """Return all sector predictions reachable from the named event.
    Falls back to the shared hardcoded chains if Neo4j is absent or
    errors out, so backtests still produce rows in dev.
    """
    if not neo4j_driver:
        return _fallback_predictions(event_name, signal_type)

    try:
        async with neo4j_driver.session() as session:
            result = await session.run(
                KG_EDGE_QUERY,
                event_name=event_name,
                signal_type=signal_type,
                country=country,
            )
            rows = await result.data()
    except Exception as e:
        logger.warning("kg_query.error", event=event_name, error=str(e))
        return _fallback_predictions(event_name, signal_type)

    out: list[KGPrediction] = []
    for r in rows:
        direction = _normalize_direction(r.get("direction"))
        if direction == "neutral":
            continue
        strength = r.get("strength")
        lag = r.get("lag_days")
        out.append(KGPrediction(
            event_name=r.get("event_name") or event_name,
            sector=r["sector"],
            direction=direction,
            strength=float(strength) if strength is not None else 0.0,
            lag_days=int(lag) if lag is not None else None,
        ))
    return out


def _fallback_predictions(event_name: str, signal_type: str) -> list[KGPrediction]:
    """Adapt the shared hardcoded fallback to KGPrediction dataclasses.
    We reuse the same data `ResearchAgent` has always fallen back to so
    behavior between the live path and the backtest is consistent."""
    rows = _fallback_kg_data(entities=[event_name], signal_types=[signal_type])
    out: list[KGPrediction] = []
    for r in rows:
        direction = _normalize_direction(r.get("sector_sentiment"))
        if direction == "neutral":
            continue
        out.append(KGPrediction(
            event_name=r.get("trigger") or event_name,
            sector=r["india_sector"],
            direction=direction,
            strength=float(r.get("strength") or 0.0),
            lag_days=None,
        ))
    return out
