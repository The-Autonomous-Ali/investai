"""
GraphRAG Neo4j Auto-Enricher — MiroFish approach.

Instead of manually maintaining Neo4j relationships,
this automatically extracts entities and relationships
from news articles and enriches the knowledge graph.

How it works:
1. New article arrives via RSS
2. LLM extracts entities (companies, sectors, events)
3. LLM identifies relationships (CAUSES, AFFECTS, CORRELATES_WITH)
4. New nodes and edges are written to Neo4j
5. Future queries automatically use this enriched graph

No external API needed — uses your existing LLM client.
"""
import json
import structlog
from datetime import datetime
from typing import Optional

from utils.llm_client import call_llm

logger = structlog.get_logger()

ENTITY_EXTRACTION_PROMPT = """You are a financial knowledge graph builder specializing in Indian markets.

Extract all entities and relationships from this news article that would be useful
for understanding how events affect Indian stock market sectors and companies.

ARTICLE: {article_text}
SOURCE: {source}
DATE: {date}

Extract and return ONLY valid JSON:
{{
  "entities": [
    {{
      "name": "Iran-Israel Conflict",
      "type": "Event",
      "properties": {{
        "event_type": "geopolitical",
        "geography": "middle_east",
        "started": "2024-10",
        "status": "ongoing"
      }}
    }},
    {{
      "name": "Brent Crude",
      "type": "Commodity",
      "properties": {{
        "unit": "USD/barrel",
        "current_price": 84.0
      }}
    }},
    {{
      "name": "Aviation",
      "type": "Sector",
      "properties": {{
        "country": "India",
        "sensitivity": "high_oil_price"
      }}
    }}
  ],
  "relationships": [
    {{
      "from": "Iran-Israel Conflict",
      "from_type": "Event",
      "relationship": "CAUSES",
      "to": "Brent Crude Price Rise",
      "to_type": "Effect",
      "properties": {{
        "strength": 0.85,
        "avg_lag_days": 1,
        "confidence": 0.82
      }}
    }},
    {{
      "from": "Brent Crude Price Rise",
      "from_type": "Effect",
      "relationship": "AFFECTS",
      "to": "Aviation",
      "to_type": "Sector",
      "properties": {{
        "sentiment": "negative",
        "strength": 0.87,
        "country": "India",
        "reason": "Higher jet fuel costs compress margins"
      }}
    }}
  ],
  "india_relevance_score": 0.0-1.0,
  "key_insight": "One sentence on why this matters for India"
}}

Focus only on relationships that affect Indian markets.
If the article has no India relevance, return {{"india_relevance_score": 0, "entities": [], "relationships": []}}
"""

CYPHER_MERGE_TEMPLATE = """
MERGE (e:{entity_type} {{name: $name}})
SET e += $properties
SET e.last_updated = $timestamp
"""

CYPHER_RELATIONSHIP_TEMPLATE = """
MATCH (a {{name: $from_name}})
MATCH (b {{name: $to_name}})
MERGE (a)-[r:{relationship}]->(b)
SET r += $properties
SET r.last_updated = $timestamp
"""


class GraphRAGEnricher:
    """
    Automatically enriches the Neo4j knowledge graph from news articles.
    Uses LLM to extract entities and relationships — no manual work needed.

    This is the MiroFish approach: instead of hardcoding relationships,
    the system learns them continuously from incoming news.
    """

    def __init__(self, neo4j_driver=None):
        self.neo4j = neo4j_driver

    async def enrich_from_article(self, article_text: str, source: str, date: str = None) -> dict:
        """
        Main entry point — takes a news article and enriches Neo4j.
        Called by Signal Watcher after each new signal is classified.
        """
        if not article_text or len(article_text) < 50:
            return {"enriched": False, "reason": "article_too_short"}

        log = logger.bind(source=source)
        log.info("graphrag.enrich_start")

        # Step 1: Extract entities and relationships using LLM
        extracted = await self._extract_entities(article_text, source, date or datetime.utcnow().strftime("%Y-%m-%d"))

        # Skip if not India-relevant
        if extracted.get("india_relevance_score", 0) < 0.3:
            log.info("graphrag.skipped_low_relevance",
                     score=extracted.get("india_relevance_score"))
            return {"enriched": False, "reason": "low_india_relevance"}

        entities      = extracted.get("entities", [])
        relationships = extracted.get("relationships", [])

        if not entities and not relationships:
            return {"enriched": False, "reason": "no_entities_found"}

        # Step 2: Write to Neo4j
        if self.neo4j:
            written = await self._write_to_graph(entities, relationships)
        else:
            written = {"entities_written": 0, "relationships_written": 0, "neo4j": "unavailable"}

        log.info("graphrag.enrich_complete",
                 entities=len(entities),
                 relationships=len(relationships),
                 neo4j_written=written)

        return {
            "enriched":            True,
            "entities_extracted":  len(entities),
            "relationships_found": len(relationships),
            "india_relevance":     extracted.get("india_relevance_score"),
            "key_insight":         extracted.get("key_insight"),
            "neo4j_result":        written,
        }

    async def _extract_entities(self, article_text: str, source: str, date: str) -> dict:
        prompt = ENTITY_EXTRACTION_PROMPT.format(
            article_text=article_text[:2000],
            source=source,
            date=date,
        )
        try:
            text = await call_llm(prompt, agent_name="graphrag_enricher")
            return json.loads(text)
        except Exception as e:
            logger.warning("graphrag.extraction_error", error=str(e))
            return {"india_relevance_score": 0, "entities": [], "relationships": []}

    async def _write_to_graph(self, entities: list, relationships: list) -> dict:
        """Write extracted entities and relationships to Neo4j."""
        entities_written      = 0
        relationships_written = 0
        timestamp             = datetime.utcnow().isoformat()

        try:
            async with self.neo4j.session() as session:

                # Write entities
                for entity in entities:
                    try:
                        await session.run(
                            f"MERGE (e:{entity['type']} {{name: $name}}) SET e += $properties SET e.last_updated = $ts",
                            name=entity["name"],
                            properties=entity.get("properties", {}),
                            ts=timestamp,
                        )
                        entities_written += 1
                    except Exception as e:
                        logger.warning("graphrag.entity_write_error",
                                       entity=entity.get("name"), error=str(e))

                # Write relationships
                for rel in relationships:
                    try:
                        rel_type = rel["relationship"].replace(" ", "_").upper()
                        cypher   = f"""
                        MERGE (a {{name: $from_name}})
                        MERGE (b {{name: $to_name}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        SET r += $properties
                        SET r.last_updated = $ts
                        """
                        await session.run(
                            cypher,
                            from_name=rel["from"],
                            to_name=rel["to"],
                            properties=rel.get("properties", {}),
                            ts=timestamp,
                        )
                        relationships_written += 1
                    except Exception as e:
                        logger.warning("graphrag.relationship_write_error",
                                       rel=rel.get("relationship"), error=str(e))

        except Exception as e:
            logger.warning("graphrag.neo4j_session_error", error=str(e))
            return {"error": str(e)}

        return {
            "entities_written":      entities_written,
            "relationships_written": relationships_written,
            "timestamp":             timestamp,
        }

    async def enrich_batch(self, articles: list) -> list:
        """
        Enrich Neo4j from multiple articles in one go.
        Called by the background worker during full RSS scan.
        """
        results = []
        for article in articles[:20]:  # Process up to 20 articles
            result = await self.enrich_from_article(
                article_text=article.get("content", article.get("title", "")),
                source=article.get("source", "unknown"),
                date=article.get("date"),
            )
            if result.get("enriched"):
                results.append(result)

        logger.info("graphrag.batch_complete",
                    total=len(articles),
                    enriched=len(results))
        return results

    async def get_graph_stats(self) -> dict:
        """Get current Neo4j graph statistics."""
        if not self.neo4j:
            return {"error": "neo4j_unavailable"}

        try:
            async with self.neo4j.session() as session:
                # Count nodes
                nodes_result = await session.run("MATCH (n) RETURN count(n) as count")
                nodes_data   = await nodes_result.data()
                node_count   = nodes_data[0]["count"] if nodes_data else 0

                # Count relationships
                rels_result = await session.run("MATCH ()-[r]->() RETURN count(r) as count")
                rels_data   = await rels_result.data()
                rel_count   = rels_data[0]["count"] if rels_data else 0

                # Count node types
                types_result = await session.run("MATCH (n) RETURN labels(n) as labels, count(n) as count")
                types_data   = await types_result.data()

                return {
                    "total_nodes":         node_count,
                    "total_relationships": rel_count,
                    "node_types":          types_data,
                    "graph_health":        "good" if node_count > 10 else "sparse",
                }
        except Exception as e:
            return {"error": str(e)}