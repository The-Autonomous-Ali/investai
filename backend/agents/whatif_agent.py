"""
What If Scenario Simulator Agent

Lets users run hypothetical scenarios through the full agent pipeline.
Examples:
  - "What if RBI cuts rates by 50bps tomorrow?"
  - "What if Brent crude crosses $120?"
  - "What if India and China sign a trade deal?"
  - "What if the US enters recession?"

Reuses all 13 existing agents — just injects a hypothetical signal
at the top of the pipeline instead of a real one.
"""
import json
import structlog
from datetime import datetime

from utils.llm_client import call_llm

logger = structlog.get_logger()

SCENARIO_PARSER_PROMPT = """You are a financial scenario interpreter for Indian markets.

The user has described a hypothetical market scenario. Parse it into a structured signal
that can be fed into the InvestAI analysis pipeline.

USER SCENARIO: {scenario}
CURRENT MARKET SNAPSHOT: {snapshot}

Convert this into a structured signal AND estimate the immediate market parameter changes.

Return ONLY valid JSON:
{{
  "scenario_title": "Clear title of the hypothetical event",
  "scenario_type": "monetary|geopolitical|commodity|fiscal|trade|corporate",
  "probability": 0.0-1.0,
  "hypothetical_signal": {{
    "title": "signal title",
    "signal_type": "monetary|geopolitical|commodity|fiscal|trade",
    "urgency": "breaking|developing|long_term",
    "importance_score": 0.0-10.0,
    "confidence": 0.8,
    "geography": "india|global|us|china|middle_east",
    "sentiment": "positive|negative|neutral",
    "entities_mentioned": ["RBI", "Repo Rate"],
    "sectors_affected": {{
      "banking": "positive",
      "real_estate": "positive"
    }},
    "india_impact": "high|medium|low",
    "chain_effects": [
      "RBI rate cut -> lower EMIs -> real estate demand rises",
      "Rate cut -> banking NIM compression -> bank stocks fall short term"
    ]
  }},
  "parameter_changes": {{
    "repo_rate_change": "-0.50%",
    "expected_nifty_move": "+1.5% to +2.5%",
    "expected_inr_move": "strengthens 0.3-0.5%",
    "expected_sectors_up": ["Real Estate", "Auto", "FMCG"],
    "expected_sectors_down": ["Banking (NIM compression)"],
    "bond_yield_change": "-20 to -30 bps"
  }},
  "key_assumptions": [
    "Inflation is below 4% at time of cut",
    "Global risk-off has not intensified"
  ],
  "what_invalidates_this": "If US Fed raises rates simultaneously, RBI cut impact is neutralized"
}}
"""

SCENARIO_IMPACT_PROMPT = """You are a senior investment strategist running a hypothetical scenario analysis for Indian markets.

HYPOTHETICAL SCENARIO: {scenario_title}
SCENARIO DETAILS: {scenario_details}
PARAMETER CHANGES: {parameter_changes}

CURRENT PORTFOLIO (if user has one): {current_portfolio}
INVESTMENT AMOUNT: {amount}
TIME HORIZON: {horizon}
USER RISK PROFILE: {risk_profile}

Compared to a baseline (no scenario), what changes in the investment strategy?

Return ONLY valid JSON:
{{
  "scenario_summary": "2-3 sentence plain English explanation of what this scenario means for Indian investors",
  "baseline_vs_scenario": {{
    "without_scenario": "What we'd recommend in normal conditions",
    "with_scenario": "What changes because of this hypothetical"
  }},
  "portfolio_impact": {{
    "positions_to_add": [
      {{"instrument": "HDFC Bank", "reason": "Rate cut boosts lending margins recovery", "conviction": "high"}}
    ],
    "positions_to_reduce": [
      {{"instrument": "Gold ETF", "reason": "Risk-on environment reduces safe haven demand", "conviction": "medium"}}
    ],
    "positions_unchanged": [
      {{"instrument": "Nifty 50 Index Fund", "reason": "Core allocation stays regardless of rate moves"}}
    ]
  }},
  "new_allocation_suggestion": {{
    "Asset Name": {{"percentage": 25, "reason": "why under this scenario"}}
  }},
  "timing_advice": "Should user act before or after this scenario plays out?",
  "probability_weighted_return": {{
    "if_scenario_happens": "Expected 3-month return",
    "if_scenario_doesnt_happen": "Expected 3-month return",
    "probability_of_scenario": 0.0-1.0,
    "expected_value": "Probability-weighted return"
  }},
  "risk_factors": [
    "What could make this scenario worse than expected"
  ],
  "monitoring_triggers": [
    "What to watch to know if this scenario is playing out"
  ],
  "action_checklist": [
    "Step 1: ...",
    "Step 2: ..."
  ]
}}
"""


class WhatIfAgent:
    """
    Scenario simulator — injects hypothetical signals into the pipeline
    and produces a full portfolio impact analysis.

    No new infrastructure needed — reuses existing LLM client.
    """

    def __init__(self, db_session=None, redis_client=None):
        self.db    = db_session
        self.redis = redis_client

    async def simulate(
        self,
        scenario: str,
        current_portfolio: dict = None,
        amount: float = 100000,
        horizon: str = "1 year",
        risk_profile: str = "moderate",
        market_snapshot: dict = None,
    ) -> dict:
        """
        Main entry point — takes a natural language scenario and returns
        full investment impact analysis.
        """
        log = logger.bind(scenario=scenario[:60])
        log.info("whatif_agent.start")

        snapshot = market_snapshot or {}

        # Step 1: Parse the scenario into a structured signal
        parsed = await self._parse_scenario(scenario, snapshot)
        log.info("whatif_agent.scenario_parsed",
                 scenario_type=parsed.get("scenario_type"),
                 probability=parsed.get("probability"))

        # Step 2: Run impact analysis
        impact = await self._analyze_impact(
            scenario_title=parsed.get("scenario_title", scenario),
            scenario_details=parsed.get("hypothetical_signal", {}),
            parameter_changes=parsed.get("parameter_changes", {}),
            current_portfolio=current_portfolio or {},
            amount=amount,
            horizon=horizon,
            risk_profile=risk_profile,
        )

        log.info("whatif_agent.complete")

        return {
            "scenario":           scenario,
            "parsed_scenario":    parsed,
            "impact_analysis":    impact,
            "generated_at":       datetime.utcnow().isoformat(),
            "disclaimer": (
                "This is a hypothetical scenario analysis for educational purposes only. "
                "It does not constitute SEBI-registered investment advice."
            ),
        }

    async def _parse_scenario(self, scenario: str, snapshot: dict) -> dict:
        prompt = SCENARIO_PARSER_PROMPT.format(
            scenario=scenario,
            snapshot=json.dumps({
                k: v for k, v in snapshot.items()
                if k in ["nifty50", "brent_crude", "usd_inr", "us_10y_yield",
                         "india_vix", "repo_rate"]
            }, indent=2) if snapshot else "{}",
        )
        text = await call_llm(prompt, agent_name="whatif_agent")
        return json.loads(text)

    async def _analyze_impact(
        self,
        scenario_title: str,
        scenario_details: dict,
        parameter_changes: dict,
        current_portfolio: dict,
        amount: float,
        horizon: str,
        risk_profile: str,
    ) -> dict:
        prompt = SCENARIO_IMPACT_PROMPT.format(
            scenario_title=scenario_title,
            scenario_details=json.dumps(scenario_details, indent=2),
            parameter_changes=json.dumps(parameter_changes, indent=2),
            current_portfolio=json.dumps(current_portfolio, indent=2)[:500],
            amount=f"{amount:,.0f}",
            horizon=horizon,
            risk_profile=risk_profile,
        )
        text = await call_llm(prompt, agent_name="whatif_agent")
        return json.loads(text)