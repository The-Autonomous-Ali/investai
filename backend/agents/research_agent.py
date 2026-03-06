"""
Research Agent — Deep analysis of signals.
Takes signals, queries the knowledge graph, and produces
a full India-specific impact analysis.
"""
import json
import structlog
from anthropic import AsyncAnthropic
from neo4j import AsyncGraphDatabase

logger = structlog.get_logger()
client = AsyncAnthropic()

RESEARCH_PROMPT = """You are an expert analyst specializing in how global and domestic events impact the Indian economy and stock markets.

Given these current market signals and their knowledge graph connections, produce a thorough impact analysis.

SIGNALS:
{signals}

KNOWLEDGE GRAPH CONNECTIONS (what these signals connect to):
{kg_connections}

CURRENT INDIA MACRO STATE:
{macro_state}

AGENT ACCURACY NOTE: {accuracy_note}

Analyze and return ONLY valid JSON:
{{
  "top_signal": "the most important signal right now",
  "impact_chain": [
    {{
      "step": 1,
      "cause": "Iran-Israel conflict",
      "effect": "Strait of Hormuz blockage risk rises",
      "confidence": 0.75
    }},
    ...
  ],
  "india_specific_analysis": "detailed paragraph on India-specific impact",
  "sectors_analysis": {{
    "strong_buy": [{{"sector": "name", "reason": "why", "instruments": ["ONGC", "Oil India ETF"]}}],
    "buy": [...],
    "neutral": [...],
    "avoid": [{{"sector": "name", "reason": "why", "risk_level": "high"}}],
    "strong_avoid": [...]
  }},
  "currency_impact": "analysis of INR impact",
  "inflation_impact": "analysis of inflation impact",
  "time_horizon": "short_term|medium_term|long_term",
  "key_assumptions": ["assumption 1", "assumption 2"],
  "confidence_score": 0.0-1.0,
  "data_quality": "high|medium|low"
}}
"""

# Cypher query to get knowledge graph connections
KG_TRAVERSAL_QUERY = """
MATCH (e:Event)-[:CAUSES*1..3]->(impact)
WHERE e.name IN $entity_names OR e.type IN $signal_types
WITH impact, e
OPTIONAL MATCH (impact)-[:AFFECTS]->(sector:Sector {country: 'India'})
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


class ResearchAgent:
    def __init__(self, db_session, neo4j_driver):
        self.db     = db_session
        self.neo4j  = neo4j_driver

    async def analyze(self, signals: list) -> dict:
        """Full research analysis for a list of signals."""
        if not signals:
            return {"error": "no_signals", "sectors_analysis": {}}

        log = logger.bind(signal_count=len(signals))
        log.info("research_agent.start")

        # Extract entities and types from signals
        entities    = []
        signal_types = []
        for s in signals[:5]:  # focus on top 5 signals
            entities.extend(s.get("entities_mentioned", []))
            if s.get("signal_type"):
                signal_types.append(s["signal_type"])

        # Query knowledge graph for connections
        kg_connections = await self._query_knowledge_graph(entities, signal_types)

        # Get current macro state
        macro_state = await self._get_macro_state()

        # Get agent accuracy note for self-calibration
        accuracy_note = await self._get_accuracy_note(signal_types)

        # Run AI analysis
        result = await self._run_analysis(
            signals, kg_connections, macro_state, accuracy_note
        )

        log.info("research_agent.complete", confidence=result.get("confidence_score"))
        return result

    async def _query_knowledge_graph(self, entities: list, signal_types: list) -> list:
        """Query Neo4j knowledge graph for impact chains."""
        if not self.neo4j:
            return self._get_fallback_kg_data(entities, signal_types)

        try:
            async with self.neo4j.session() as session:
                result = await session.run(
                    KG_TRAVERSAL_QUERY,
                    entity_names=entities[:10],
                    signal_types=signal_types,
                )
                records = await result.data()
                return records
        except Exception as e:
            logger.warning("research_agent.kg_error", error=str(e))
            return self._get_fallback_kg_data(entities, signal_types)

    def _get_fallback_kg_data(self, entities: list, signal_types: list) -> list:
        """Fallback knowledge graph data when Neo4j is unavailable."""
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
        }

        connections = []
        for stype in signal_types:
            connections.extend(base_connections.get(stype, []))
        return connections if connections else base_connections["monetary"]

    async def _get_macro_state(self) -> dict:
        """Get current India macro indicators."""
        # In production: fetch from NSE/RBI APIs
        return {
            "repo_rate":           "6.50%",
            "cpi_inflation":       "5.10%",
            "gdp_growth":          "7.20%",
            "current_account_deficit": "-1.8% of GDP",
            "forex_reserves":      "$620B",
            "fii_ytd_flows":       "-$2.1B",
            "dii_ytd_flows":       "+$8.4B",
            "rupee_ytd_change":    "-1.2%",
            "nifty_pe":            "21.4x",
            "india_vix":           "14.2 (low)",
        }

    async def _get_accuracy_note(self, signal_types: list) -> str:
        """Get self-calibration note based on past accuracy."""
        from models.models import AgentPerformance
        perf = self.db.query(AgentPerformance).filter(
            AgentPerformance.agent_name == "research_agent"
        ).first()

        if not perf or not perf.signal_type_accuracy:
            return "Insufficient historical data for calibration."

        notes = []
        for stype in signal_types:
            acc = perf.signal_type_accuracy.get(stype)
            if acc:
                notes.append(f"Your historical accuracy on {stype} signals is {acc:.0%}.")
                if acc < 0.6:
                    notes.append(f"Apply extra caution on {stype} predictions.")

        return " ".join(notes) if notes else "No calibration data available yet."

    async def _run_analysis(self, signals, kg_connections, macro_state, accuracy_note) -> dict:
        """Run the main AI analysis."""
        signals_text = json.dumps([
            {k: v for k, v in s.items() if k in [
                "title", "signal_type", "urgency", "importance_score",
                "entities_mentioned", "sectors_affected", "chain_effects"
            ]}
            for s in signals[:5]
        ], indent=2)

        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": RESEARCH_PROMPT.format(
                    signals=signals_text,
                    kg_connections=json.dumps(kg_connections[:15], indent=2),
                    macro_state=json.dumps(macro_state, indent=2),
                    accuracy_note=accuracy_note,
                )
            }]
        )

        text = response.content[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
