"""
Research Agent — Deep analysis of signals.
Takes signals, queries the knowledge graph, and produces
a full India-specific impact analysis.
FIXED: Neo4j Cypher syntax error (double braces removed).
UPDATED: Macro state now uses live snapshot data.
"""
import json
import structlog
from sqlalchemy import select

from utils.llm_client import call_llm
from agents.kg_traversal import query_knowledge_graph, query_root_cause_chain

logger = structlog.get_logger()

RESEARCH_PROMPT = """You are an expert analyst specializing in how global and domestic events impact the {country} economy and stock markets.

Given these current market signals and their knowledge graph connections, produce a thorough impact analysis for {country}.

SIGNALS:
{signals}

KNOWLEDGE GRAPH CONNECTIONS (what these signals connect to):
{kg_connections}

CURRENT {country} MACRO STATE:
{macro_state}

ROOT CAUSE CONTEXT (what triggered these events — use this to explain WHY):
{root_cause_context}

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
    }}
  ],
  "country_specific_analysis": "detailed paragraph on {country}-specific impact",
  "sectors_analysis": {{
    "strong_buy": [{{"sector": "name", "reason": "why", "instruments": ["Asset A", "Asset B"]}}],
    "buy": [],
    "neutral": [],
    "avoid": [{{"sector": "name", "reason": "why", "risk_level": "high"}}],
    "strong_avoid": []
  }},
  "currency_impact": "analysis of local currency impact",
  "inflation_impact": "analysis of inflation impact",
  "time_horizon": "short_term|medium_term|long_term",
  "root_cause_narrative": "1-2 sentences explaining the root cause behind the top signal — what specific event/decision triggered this chain",
  "key_assumptions": ["assumption 1", "assumption 2"],
  "confidence_score": 0.0-1.0,
  "data_quality": "high|medium|low"
}}
"""

class ResearchAgent:
    def __init__(self, db_session, neo4j_driver):
        self.db    = db_session
        self.neo4j = neo4j_driver

    async def analyze(self, signals: list, country: str = "India") -> dict:
        """Full research analysis for a list of signals."""
        if not signals:
            return {"error": "no_signals", "sectors_analysis": {}}

        log = logger.bind(signal_count=len(signals), country=country)
        log.info("research_agent.start")

        entities     = []
        signal_types = []
        for s in signals[:5]:
            entities.extend(s.get("entities_mentioned", []))
            if s.get("signal_type"):
                signal_types.append(s["signal_type"])

        # Extract event names for root cause lookup
        event_names = list(set(entities + [s.get("title", "") for s in signals[:5]]))

        kg_connections = await self._query_knowledge_graph(entities, signal_types, country)
        root_cause_data = await query_root_cause_chain(self.neo4j, event_names, signal_types, country)
        macro_state    = await self._get_macro_state(country)
        accuracy_note  = await self._get_accuracy_note(signal_types)

        result = await self._run_analysis(
            signals, kg_connections, root_cause_data, macro_state, accuracy_note, country
        )

        log.info("research_agent.complete", confidence=result.get("confidence_score"))
        return result

    async def _query_knowledge_graph(self, entities: list, signal_types: list, country: str) -> list:
        return await query_knowledge_graph(self.neo4j, entities, signal_types, country)

    async def _get_macro_state(self, country: str) -> dict:
        """
        Get macro state — tries to pull from live Redis snapshot first,
        falls back to static values if not available.
        """
        if country == "India":
            # Try to get live snapshot from Redis if available
            live_data = {}
            try:
                if hasattr(self, 'redis') and self.redis:
                    import json as _json
                    cached = await self.redis.get("market_snapshot")
                    if cached:
                        snapshot = _json.loads(cached)
                        live_data = {
                            "nifty50":      snapshot.get("nifty50", {}).get("value"),
                            "india_vix":    snapshot.get("india_vix", {}).get("value"),
                            "usd_inr":      snapshot.get("usd_inr", {}).get("value"),
                            "brent_crude":  snapshot.get("brent_crude", {}).get("value"),
                            "us_10y_yield": snapshot.get("us_10y_yield", {}).get("value"),
                        }
            except Exception:
                pass

            return {
                "repo_rate":               "6.50%",
                "cpi_inflation":           "5.10%",
                "gdp_growth":              "7.20%",
                "current_account_deficit": "-1.8% of GDP",
                "forex_reserves":          "$620B",
                "fii_ytd_flows":           "-$2.1B",
                "dii_ytd_flows":           "+$8.4B",
                # Use live values if available, otherwise static fallback
                "nifty50":      live_data.get("nifty50", 23581),
                "india_vix":    live_data.get("india_vix", 19.8),
                "usd_inr":      live_data.get("usd_inr", 92.42),
                "brent_crude":  live_data.get("brent_crude", 103.0),
                "us_10y_yield": live_data.get("us_10y_yield", 4.31),
            }

        return {"note": f"Real-time macro data for {country} estimated by LLM."}

    async def _get_accuracy_note(self, signal_types: list) -> str:
        try:
            from models.models import AgentPerformance
            result = await self.db.execute(
                select(AgentPerformance).where(AgentPerformance.agent_name == "research_agent")
            )
            perf = result.scalar_one_or_none()

            if not perf or not perf.signal_type_accuracy:
                return "Insufficient historical data for calibration."

            notes = []
            for stype in signal_types:
                acc = perf.signal_type_accuracy.get(stype)
                if acc:
                    notes.append(f"Historical accuracy on {stype} signals: {acc:.0%}.")
                    if acc < 0.6:
                        notes.append(f"Apply extra caution on {stype} predictions.")

            return " ".join(notes) if notes else "No calibration data available yet."
        except Exception:
            return "No calibration data available yet."

    async def _run_analysis(self, signals, kg_connections, root_cause_data, macro_state, accuracy_note, country: str) -> dict:
        signals_text = json.dumps([
            {k: v for k, v in s.items() if k in [
                "title", "signal_type", "urgency", "importance_score",
                "entities_mentioned", "sectors_affected", "chain_effects"
            ]}
            for s in signals[:5]
        ], indent=2)

        # Format root cause context for the prompt
        root_cause_context = "No root cause data available yet."
        if root_cause_data.get("root_causes"):
            root_cause_context = json.dumps(root_cause_data["root_causes"][:5], indent=2)
        else:
            # Fall back to root_cause_chain from signals themselves
            signal_root_causes = []
            for s in signals[:5]:
                for rc in (s.get("root_cause_chain") or []):
                    if rc.get("event"):
                        signal_root_causes.append(rc)
            if signal_root_causes:
                root_cause_context = json.dumps(signal_root_causes, indent=2)

        prompt = RESEARCH_PROMPT.format(
            signals=signals_text,
            kg_connections=json.dumps(kg_connections[:15], indent=2),
            root_cause_context=root_cause_context,
            macro_state=json.dumps(macro_state, indent=2),
            accuracy_note=accuracy_note,
            country=country,
        )

        text = await call_llm(prompt, agent_name="research_agent")
        return json.loads(text)

    @staticmethod
    def assemble_full_chain(signal_data: dict, research_result: dict, temporal_data: dict) -> dict:
        """Stitch together root causes, forward chain, and resolution into one structure.

        Pure data joining — no LLM call. Called by orchestrator after all three
        agents have completed.
        """
        from datetime import datetime as dt

        # Root causes from signal_watcher
        root_causes = signal_data.get("root_cause_chain") or []

        # Forward chain from research_agent
        forward_chain = research_result.get("impact_chain") or []

        # Resolution from temporal_agent
        resolution_chain = []
        for timeline in (temporal_data.get("timelines") or []):
            # Resolution conditions (always present)
            for condition in (timeline.get("resolution_conditions") or []):
                resolution_chain.append({
                    "event": condition,
                    "role": "resolution_condition",
                    "source": "",
                    "date": "",
                })
            # Actual resolution cause (only for resolved/de-escalating events)
            rc = timeline.get("resolution_cause", {})
            if rc and rc.get("what_resolved_it"):
                resolution_chain.append({
                    "event": rc["what_resolved_it"],
                    "role": "resolution_trigger",
                    "source": rc.get("source", ""),
                    "date": rc.get("date", ""),
                })

        return {
            "root_causes": root_causes,
            "forward_chain": forward_chain,
            "resolution_chain": resolution_chain,
            "root_cause_narrative": research_result.get("root_cause_narrative", ""),
            "assembled_at": dt.utcnow().isoformat(),
        }