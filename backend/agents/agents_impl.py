"""
Portfolio Agent — Sector strength analysis (no specific allocations — SEBI Option 1).
Tax Agent — Optimises for country-specific tax efficiency.
Critic Agent — Stress-tests recommendations.
Memory Agent — User context store.
Temporal Agent — Event lifecycle assessment.
Watchdog Agent — Conflict and anomaly detection.
Pattern Matcher Agent — Historical analogue finder.
"""
import json
import os
import structlog
from datetime import datetime, timedelta

from utils.llm_client import call_llm

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO AGENT
# ─────────────────────────────────────────────────────────────────────────────

PORTFOLIO_PROMPT = """You are a direct, evidence-driven sector analyst for {country} markets.

Your job: given the current signals and research, state CLEARLY which sectors show BUY signals and which show AVOID signals right now. Be decisive. Back every call with specific data from the inputs.

RESEARCH ANALYSIS: {research}
HISTORICAL PATTERNS: {patterns}
USER PROFILE: {user_profile}
TIME HORIZON: {horizon}
CRITIC FEEDBACK (if any): {critic_feedback}

Return ONLY valid JSON:
{{
  "sector_signals": [
    {{
      "sector": "IT",
      "signal": "BUY",
      "signal_strength": "strong|moderate|weak",
      "confidence": 0.0-1.0,
      "primary_driver": "The single most important reason — cite specific data from the research",
      "supporting_evidence": ["Evidence point 1 from data", "Evidence point 2 from data"],
      "what_would_invalidate": "The specific condition that would flip this signal",
      "time_horizon": "weeks|1-3 months|3-6 months"
    }}
  ],
  "sectors_to_research": [{{"sector": "name", "signal": "BUY|NEUTRAL|AVOID", "reason": "specific data-backed reason", "key_signals": ["signal driving this"]}}],
  "sectors_showing_risk": [{{"sector": "name", "signal": "AVOID", "reason": "specific risk from data", "risk_level": "high|medium"}}],
  "rebalancing_triggers": [
    {{"condition": "Brent crosses $95", "action": "Strengthen BUY on Oil & Gas", "urgency": "high|medium"}}
  ],
  "narrative": "2-paragraph direct assessment — state what the signals mean for Indian markets right now. No hedging.",
  "analysis_confidence": 0.0-1.0,
  "review_date": "YYYY-MM-DD"
}}
"""


class PortfolioAgent:
    def __init__(self, db_session):
        self.db = db_session

    async def run(self, inputs: dict) -> dict:
        research  = inputs.get("research_agent", {})
        patterns  = inputs.get("pattern_matcher", {})
        profile   = inputs.get("user_profile", {})
        amount    = inputs.get("amount", 100000)
        horizon   = inputs.get("horizon", "1 year")
        country   = inputs.get("country", "India")
        feedback  = inputs.get("critic_feedback", "None")

        prompt = PORTFOLIO_PROMPT.format(
            research=json.dumps(research, indent=2)[:2000],
            patterns=json.dumps(patterns, indent=2)[:1000],
            user_profile=json.dumps(profile, indent=2)[:500],
            amount=f"{amount:,.0f}",
            horizon=horizon,
            country=country,
            critic_feedback=feedback,
        )

        try:
            text = await call_llm(prompt, agent_name="portfolio_agent")
            return json.loads(text)
        except Exception as e:
            logger.warning("portfolio_agent.llm_failed", error=str(e)[:200])
            return {"sectors_to_research": [], "narrative": "Analysis unavailable", "analysis_confidence": 0.3}


# ─────────────────────────────────────────────────────────────────────────────
# TAX AGENT
# ─────────────────────────────────────────────────────────────────────────────

TAX_PROMPT = """You are a tax optimization specialist for {country}.

Review this portfolio allocation and optimize for {country} tax efficiency.

ALLOCATION: {allocation}
USER PROFILE: {profile}
Tax bracket: {tax_bracket}%

If the country is India, consider:
- STCG (15%) vs LTCG (10% above ₹1L) for equity
- Section 80C: ELSS funds (₹1.5L limit)
- Sovereign Gold Bonds: tax-free on maturity
...

If the country is NOT India, provide best-effort general tax optimization advice based on common global standards.

Return ONLY valid JSON:
{{
  "optimizations": [
    {{
      "original": "Asset A",
      "suggestion": "Suggestion B",
      "tax_benefit": "Why it saves tax",
      "annual_saving_estimate": 3000
    }}
  ],
  "tax_advantaged_recommendation": {{"amount": 50000, "benefit": "Save X in taxes"}},
  "holding_period_advice": "Advice on how long to hold assets",
  "post_tax_return_estimate": "X% post-tax vs Y% pre-tax",
  "estimated_annual_tax_saving": 28000
}}
"""


class TaxAgent:
    async def optimize(self, portfolio: dict, profile: dict, country: str = "India") -> dict:
        prompt = TAX_PROMPT.format(
            allocation=json.dumps(portfolio.get("allocation", {}), indent=2),
            profile=json.dumps({k: v for k, v in profile.items() if k in [
                "risk_tolerance", "experience_level", "investment_horizon"
            ]}, indent=2),
            tax_bracket=profile.get("tax_bracket", 30),
            country=country,
        )

        try:
            text = await call_llm(prompt, agent_name="tax_agent")
            return json.loads(text)
        except Exception as e:
            logger.warning("tax_agent.llm_failed", error=str(e)[:200])
            return {"optimizations": [], "post_tax_return_estimate": "unavailable"}


# ─────────────────────────────────────────────────────────────────────────────
# CRITIC AGENT
# ─────────────────────────────────────────────────────────────────────────────

CRITIC_PROMPT = """You are a risk-focused critic reviewing an AI-generated investment recommendation.
Your job is to CHALLENGE and STRESS-TEST this recommendation.

RECOMMENDATION: {portfolio}
TAX PLAN: {tax}
SIGNALS USED: {signals}
USER PROFILE: {user_profile}
CONFLICTS DETECTED: {conflicts}

Challenge this recommendation by asking:
1. What assumptions is this making? Are they all valid?
2. Under what conditions would this advice be completely wrong?
3. Is there a bearish/contrarian interpretation of the same signals?
4. Does the user's existing portfolio create concentration risk?
5. Is this suitable for this user's risk tolerance and experience?
6. What is the single biggest risk being ignored?

Return ONLY valid JSON:
{{
  "verdict": "PASS|REVISE|REJECT",
  "overall_quality": 0.0-1.0,
  "risks": [
    "If ceasefire happens next week, oil reversal would hurt ONGC position",
    "User has 40% in large caps already — this adds more large cap concentration"
  ],
  "feedback": "Specific actionable feedback if REVISE (empty string if PASS)",
  "what_would_make_this_wrong": "The key assumption that, if false, breaks this advice",
  "suitability_check": "PASS|FAIL",
  "suitability_notes": "any suitability concerns"
}}

Be strict but fair. REJECT only if advice is dangerous. REVISE if it needs adjustment. PASS if solid.
"""


class CriticAgent:
    async def review(self, inputs: dict) -> dict:
        prompt = CRITIC_PROMPT.format(
            portfolio=json.dumps(inputs.get("portfolio", {}), indent=2)[:1500],
            tax=json.dumps(inputs.get("tax", {}), indent=2)[:500],
            signals=json.dumps(inputs.get("signals", {}).get("signals", [])[:3], indent=2)[:500],
            user_profile=json.dumps(inputs.get("user_profile", {}), indent=2)[:400],
            conflicts=json.dumps(inputs.get("conflicts", []), indent=2),
        )

        try:
            text = await call_llm(prompt, agent_name="critic_agent")
            return json.loads(text)
        except Exception as e:
            logger.warning("critic_agent.llm_failed", error=str(e)[:200])
            return {"verdict": "PASS", "overall_quality": 0.5, "risks": [], "feedback": ""}


# ─────────────────────────────────────────────────────────────────────────────
# MEMORY AGENT
# ─────────────────────────────────────────────────────────────────────────────

class MemoryAgent:
    def __init__(self, db_session):
        self.db = db_session

    async def get_user_context(self, user_id: str) -> dict:
        from models.models import User, AdviceRecord, PortfolioItem
        from sqlalchemy import select

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {}

        result = await self.db.execute(
            select(AdviceRecord)
            .where(AdviceRecord.user_id == user_id)
            .order_by(AdviceRecord.created_at.desc())
            .limit(5)
        )
        past_advice = result.scalars().all()

        result = await self.db.execute(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == user_id, PortfolioItem.is_active == True)
        )
        holdings = result.scalars().all()

        total_current_value = sum(
            ((h.current_price or h.avg_buy_price or 0) * (h.quantity or 0))
            for h in holdings
        )

        return {
            "risk_tolerance":        user.risk_tolerance.value if user.risk_tolerance else "moderate",
            "experience_level":      user.experience_level,
            "tax_bracket":           user.tax_bracket,
            "avoid_sectors":         user.avoid_sectors or [],
            "preferred_instruments": user.preferred_instruments or [],
            "state":                 user.state,
            "country":               user.country,
            "subscription_tier":     user.subscription_tier.value if user.subscription_tier else "free",
            "past_advice": [
                {
                    "date":      a.created_at.isoformat() if a.created_at else None,
                    "query":     a.user_query,
                    "narrative": (a.narrative or "")[:200],
                    "rating":    a.advice_rating,
                }
                for a in past_advice
            ],
            "current_holdings": [
                {"symbol": h.symbol, "name": h.name, "sector": h.sector, "instrument_type": h.instrument_type}
                for h in holdings
            ],
            "current_holdings_detail": [
                {
                    "id": h.id,
                    "symbol": h.symbol,
                    "name": h.name,
                    "sector": h.sector,
                    "instrument_type": h.instrument_type,
                    "quantity": h.quantity,
                    "avg_buy_price": h.avg_buy_price,
                    "current_price": h.current_price,
                    "invested_value": round((h.avg_buy_price or 0) * (h.quantity or 0), 2),
                    "current_value": round((h.current_price or h.avg_buy_price or 0) * (h.quantity or 0), 2),
                    "pnl": round(((h.current_price or h.avg_buy_price or 0) - (h.avg_buy_price or 0)) * (h.quantity or 0), 2),
                    "pnl_pct": round((((h.current_price or h.avg_buy_price or 0) - (h.avg_buy_price or 0)) / (h.avg_buy_price or 1)) * 100, 2)
                               if h.avg_buy_price else 0,
                    "buy_date": h.buy_date.isoformat() if h.buy_date else None,
                    "weight_pct": round((((h.current_price or h.avg_buy_price or 0) * (h.quantity or 0)) / total_current_value) * 100, 2)
                                 if total_current_value > 0 else 0,
                }
                for h in holdings
            ],
            "portfolio_summary": {
                "total_holdings": len(holdings),
                "total_current_value": round(total_current_value, 2),
            },
        }

    async def store_advice(self, user_id: str, advice_data: dict):
        """Store advice record — skips silently if user doesn't exist (e.g. demo_user)."""
        try:
            from models.models import AdviceRecord, User
            from sqlalchemy import select

            # Check user exists before inserting — avoids foreign key violation
            result = await self.db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                logger.warning("memory_agent.store_advice_skipped",
                               reason="user_not_found", user_id=user_id)
                return

            rec = AdviceRecord(
                user_id=user_id,
                user_query=advice_data.get("query"),
                allocation_plan=advice_data.get("recommendation", {}).get("allocation"),
                sectors_to_buy=advice_data.get("recommendation", {}).get("sectors_to_buy"),
                sectors_to_avoid=advice_data.get("recommendation", {}).get("sectors_to_avoid"),
                rebalancing_triggers=advice_data.get("recommendation", {}).get("rebalancing_triggers"),
                tax_optimizations=advice_data.get("recommendation", {}).get("tax_optimizations"),
                narrative=advice_data.get("recommendation", {}).get("narrative"),
                reasoning_chain=advice_data.get("recommendation", {}).get("reasoning_chain"),
                confidence_score=advice_data.get("recommendation", {}).get("confidence_score"),
                triggering_signals=advice_data.get("signals_used"),
                market_snapshot=advice_data.get("market_snapshot"),
                critic_verdict=advice_data.get("critic_verdict"),
                review_date=datetime.utcnow() + timedelta(days=90),
            )
            self.db.add(rec)
            await self.db.commit()

        except Exception as e:
            await self.db.rollback()
            logger.warning("memory_agent.store_advice_error", error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# TEMPORAL AGENT
# ─────────────────────────────────────────────────────────────────────────────

TEMPORAL_PROMPT = """You are a temporal analysis specialist. Classify the lifecycle stage and prediction timeline for these market events.

SIGNALS: {signals}
CURRENT DATE: {today}

For each significant signal, assess:
1. What type of event is this? (micro/short/medium/long term)
2. Where is it in its lifecycle?
3. What are the resolution conditions?
4. What is the prediction confidence for tomorrow, this week, this month?

Return ONLY valid JSON:
{{
  "timelines": [
    {{
      "signal_title": "Iran-Israel conflict",
      "duration_type": "medium_term",
      "lifecycle_stage": "escalating",
      "estimated_duration_days": 60,
      "tomorrow_prediction": {{"summary": "Oil likely stays elevated", "confidence": 0.78}},
      "week_prediction": {{"summary": "Watch for UN meetings", "confidence": 0.61}},
      "month_prediction": {{"summary": "Base case: conflict contained", "confidence": 0.44}},
      "resolution_conditions": ["Ceasefire brokered", "Oil demand destruction"],
      "escalation_signals": ["Hormuz traffic drops 20%", "Crude crosses $105"],
      "de_escalation_signals": ["UN session called", "Oil below $88"],
      "probability_scenarios": {{
        "best_case": {{"desc": "Ceasefire in 3 weeks", "probability": 0.30, "timeline_days": 21}},
        "base_case": {{"desc": "Drags 2-3 months", "probability": 0.50, "timeline_days": 75}},
        "worst_case": {{"desc": "Hormuz blocked", "probability": 0.20, "timeline_days": 180}}
      }},
      "resolution_cause": {{
        "what_resolved_it": "Specific public event that caused de-escalation (empty string if not yet resolved)",
        "source": "Who reported it",
        "date": "When it happened",
        "confidence": 0.0-1.0
      }}
    }}
  ],
  "recommended_review_date": "YYYY-MM-DD",
  "overall_market_phase": "cautious|neutral|optimistic"
}}

NOTE: Only populate resolution_cause with real data when lifecycle_stage is "de_escalating", "fading", or "resolved". For ongoing events, set what_resolved_it to an empty string.
"""


class TemporalAgent:
    def __init__(self, db_session):
        self.db = db_session

    async def assess_timelines(self, signals: list) -> dict:
        if not signals:
            return {"timelines": [], "overall_market_phase": "neutral"}

        prompt = TEMPORAL_PROMPT.format(
            signals=json.dumps([
                {k: v for k, v in s.items() if k in [
                    "title", "signal_type", "urgency", "importance_score",
                    "entities_mentioned", "stage"
                ]}
                for s in signals[:5]
            ], indent=2),
            today=datetime.utcnow().strftime("%Y-%m-%d"),
        )

        try:
            text = await call_llm(prompt, agent_name="temporal_agent")
            return json.loads(text)
        except Exception as e:
            logger.warning("temporal_agent.llm_failed", error=str(e)[:200])
            return {"timelines": [], "overall_market_phase": "neutral"}


# ─────────────────────────────────────────────────────────────────────────────
# WATCHDOG AGENT
# ─────────────────────────────────────────────────────────────────────────────

class WatchdogAgent:
    async def check(self, agent_outputs: dict) -> list:
        conflicts = []

        research_output  = agent_outputs.get("research_agent", {})
        pattern_output   = agent_outputs.get("pattern_matcher", {})
        portfolio_output = agent_outputs.get("portfolio_agent", {})

        r_conf = research_output.get("confidence_score", 0.5)
        p_conf = pattern_output.get("confidence_score", 0.5) if pattern_output else 0.5
        if abs(r_conf - p_conf) > 0.4:
            conflicts.append({
                "type": "CONFIDENCE_GAP",
                "severity": "low",
                "message": f"Research confidence ({r_conf:.0%}) vs Pattern confidence ({p_conf:.0%}) differ significantly",
                "action": "add_uncertainty_disclosure",
            })

        research_avoid = {s["sector"] for s in research_output.get("sectors_analysis", {}).get("avoid", [])}
        portfolio_buy  = {s["sector"] for s in portfolio_output.get("sectors_to_buy", [])} if portfolio_output else set()
        contradictions = research_avoid & portfolio_buy
        if contradictions:
            conflicts.append({
                "type": "CONFLICT",
                "severity": "high",
                "message": f"Research says avoid {contradictions} but Portfolio says buy them",
                "action": "flag_and_pause",
            })

        if portfolio_output:
            allocation = portfolio_output.get("allocation", {})
            suspicious = [k for k in allocation.keys() if len(k) > 50]
            if suspicious:
                conflicts.append({
                    "type": "HALLUCINATION_RISK",
                    "severity": "critical",
                    "message": f"Unusually long instrument names detected: {suspicious[:2]}",
                    "action": "reject_output_request_retry",
                })

        return conflicts


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN MATCHER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class PatternMatcherAgent:
    PATTERN_PROMPT = """You are a market historian specializing in {country} and global markets.

Find historical analogues for these current signals and what happened to {country} markets.

CURRENT SIGNALS: {signals}

Analyze and return ONLY valid JSON:
{{
  "best_analogues": [
    {{
      "year": 2022,
      "event": "War + Oil spike",
      "similarity_score": 84,
      "similarity_reasons": ["Oil above $90", "Local currency weakness"],
      "what_happened": {{
        "Market_3m": "-5.8%",
        "Aviation": "-22%",
        "Energy": "+34%",
        "Gold": "+11%"
      }},
      "key_lesson": "description of historical lesson"
    }}
  ],
  "pattern_quality": "high|medium|low",
  "confidence_score": 0.0-1.0,
  "caveat": "any important differences between then and now"
}}
"""

    def __init__(self, db_session):
        self.db = db_session

    async def find_patterns(self, signals: list, country: str = "India") -> dict:
        if not signals:
            return {"best_analogues": [], "confidence_score": 0.3}

        prompt = self.PATTERN_PROMPT.format(
            signals=json.dumps([
                {k: v for k, v in s.items() if k in [
                    "title", "signal_type", "entities_mentioned", "sectors_affected"
                ]}
                for s in signals[:5]
            ], indent=2),
            country=country,
        )

        try:
            text = await call_llm(prompt, agent_name="pattern_matcher")
            return json.loads(text)
        except Exception as e:
            logger.warning("pattern_matcher.llm_failed", error=str(e)[:200])
            return {"best_analogues": [], "confidence_score": 0.3}
