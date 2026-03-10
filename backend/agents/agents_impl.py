"""
Portfolio Agent — Builds specific allocation plans.
"""
import json
import os
import google.generativeai as genai
from anthropic import AsyncAnthropic
from datetime import datetime, timedelta

def get_anthropic_client():
    return AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_gemini_model(model_name=None):
    model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    return genai.GenerativeModel(model_name=model_name)

PORTFOLIO_PROMPT = """You are a portfolio construction specialist for {country} retail investors.

BUILD A SPECIFIC ALLOCATION PLAN based on:

RESEARCH ANALYSIS: {research}
HISTORICAL PATTERNS: {patterns}
USER PROFILE: {user_profile}
INVESTMENT AMOUNT: {amount} (in local currency)
TIME HORIZON: {horizon}
CRITIC FEEDBACK (if any): {critic_feedback}

Rules:
- Never suggest more than 6-7 different instruments (too complex for retail)
- Always include a liquid/emergency buffer (minimum 10%)
- Respect user's avoid_sectors list
- Match risk level to user's risk_tolerance
- For moderate risk: max 60% equity
- Always name specific instruments (ETFs/index funds available in {country} are preferred)
- Include specific entry price ranges where possible

Return ONLY valid JSON:
{{
  "allocation": {{
    "Asset Name": {{"percentage": 25, "amount": 25000, "instrument_type": "etf/fund/stock", "reason": "why"}},
    ...
  }},
  "sectors_to_buy": [{{"sector": "name", "reason": "why", "instruments": ["specific fund/stock"]}}],
  "sectors_to_avoid": [{{"sector": "name", "reason": "why", "risk": "specific risk"}}],
  "rebalancing_triggers": [
    {{"condition": "Brent crude crosses $110", "action": "Reduce sensitive sectors, increase oil beneficiaries"}}
  ],
  "step_by_step_actions": [
    "Step 1: Open brokerage account in {country} if not already",
    "Step 2: Invest X in Y"
  ],
  "narrative": "3-paragraph explanation for the user in simple language",
  "confidence_score": 0.0-1.0,
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

        provider = os.getenv("AI_PROVIDER", "gemini")

        if provider == "anthropic":
            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
            model = get_gemini_model()
            response = await model.generate_content_async(prompt)
            text = response.text

        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)


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

If the country is NOT India, provide best-effort general tax optimization advice based on common global standards (like capital gains holding periods, tax-advantaged accounts like 401k/IRA/ISA, etc.).

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

        provider = os.getenv("AI_PROVIDER", "gemini")

        if provider == "anthropic":
            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
            model = get_gemini_model()
            response = await model.generate_content_async(prompt)
            text = response.text

        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)


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

        provider = os.getenv("AI_PROVIDER", "gemini")

        if provider == "anthropic":
            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
            model = get_gemini_model()
            # Gemini text generation
            response = await model.generate_content_async(prompt)
            text = response.text

        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────

class MemoryAgent:
    def __init__(self, db_session):
        self.db = db_session

    async def get_user_context(self, user_id: str) -> dict:
        from models.models import User, AdviceRecord, PortfolioItem
        from sqlalchemy import select

        # FIXED: Use select() for async session
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            return {}

        # FIXED: Use select() for async session
        result = await self.db.execute(
            select(AdviceRecord)
            .where(AdviceRecord.user_id == user_id)
            .order_by(AdviceRecord.created_at.desc())
            .limit(5)
        )
        past_advice = result.scalars().all()

        # FIXED: Use select() for async session
        result = await self.db.execute(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == user_id, PortfolioItem.is_active == True)
        )
        holdings = result.scalars().all()

        return {
            "risk_tolerance":      user.risk_tolerance,
            "experience_level":    user.experience_level,
            "tax_bracket":         user.tax_bracket,
            "avoid_sectors":       user.avoid_sectors or [],
            "preferred_instruments": user.preferred_instruments or [],
            "state":               user.state,
            "subscription_tier":   user.subscription_tier,
            "past_advice":         [
                {
                    "date":       a.created_at.isoformat() if a.created_at else None,
                    "query":      a.user_query,
                    "narrative":  (a.narrative or "")[:200],
                    "rating":     a.advice_rating,
                }
                for a in past_advice
            ],
            "current_holdings":    [
                {"symbol": h.symbol, "sector": h.sector, "instrument_type": h.instrument_type}
                for h in holdings
            ],
        }

    async def store_advice(self, user_id: str, advice_data: dict):
        from models.models import AdviceRecord
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
        await self.db.commit() # FIXED: async commit


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
      }}
    }}
  ],
  "recommended_review_date": "YYYY-MM-DD",
  "overall_market_phase": "cautious|neutral|optimistic"
}}
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

        provider = os.getenv("AI_PROVIDER", "gemini")

        if provider == "anthropic":
            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
            model = get_gemini_model()
            response = await model.generate_content_async(prompt)
            text = response.text

        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────

class WatchdogAgent:
    """Monitors all agent outputs for conflicts, reversals, and anomalies."""

    async def check(self, agent_outputs: dict) -> list:
        conflicts = []

        signal_output   = agent_outputs.get("signal_watcher", {})
        research_output = agent_outputs.get("research_agent", {})
        pattern_output  = agent_outputs.get("pattern_matcher", {})
        portfolio_output = agent_outputs.get("portfolio_agent", {})

        # Check 1: Confidence gap between research and pattern matcher
        r_conf = research_output.get("confidence_score", 0.5)
        p_conf = pattern_output.get("confidence_score", 0.5) if pattern_output else 0.5
        if abs(r_conf - p_conf) > 0.4:
            conflicts.append({
                "type": "CONFIDENCE_GAP",
                "severity": "low",
                "message": f"Research confidence ({r_conf:.0%}) vs Pattern confidence ({p_conf:.0%}) differ significantly",
                "action": "add_uncertainty_disclosure",
            })

        # Check 2: Sector contradiction between research and portfolio
        research_avoid  = {s["sector"] for s in research_output.get("sectors_analysis", {}).get("avoid", [])}
        portfolio_buy   = {s["sector"] for s in portfolio_output.get("sectors_to_buy", [])} if portfolio_output else set()
        contradictions  = research_avoid & portfolio_buy
        if contradictions:
            conflicts.append({
                "type": "CONFLICT",
                "severity": "high",
                "message": f"Research says avoid {contradictions} but Portfolio says buy them",
                "action": "flag_and_pause",
            })

        # Check 3: Hallucination risk — check for unknown instruments
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

class PatternMatcherAgent:
    """Finds historical analogues for current market conditions."""

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

        provider = os.getenv("AI_PROVIDER", "gemini")

        if provider == "anthropic":
            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
            model = get_gemini_model()
            response = await model.generate_content_async(prompt)
            text = response.text

        text = text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
