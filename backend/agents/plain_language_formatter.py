"""
Plain Language Formatter — Translates technical analysis into simple language.

Mission: A person with zero financial background should be able to read
this output and UNDERSTAND what is happening in the market and which
companies are relevant — so they can do their own research and decide.

The "Rickshaw Driver Test": If someone who has saved Rs 50,000 reads this,
will they understand what is going on and know what to research next?

SEBI Option 1: Show analysis, user decides. No buy/sell recommendations.
"""
import json
import structlog
from utils.llm_client import call_llm

logger = structlog.get_logger()

PLAIN_LANGUAGE_PROMPT = """You are translating a complex market analysis into simple language
that ANY Indian person — even with zero financial background — can understand.

TECHNICAL ANALYSIS:
{technical_data}

COMPANY DATA:
{fundamental_data}

ROOT CAUSE CONTEXT (use this to explain WHY things are happening — weave it naturally into your explanation):
{causal_chain_context}

USER CONTEXT:
- They have about Rs {amount} they are considering investing
- Risk tolerance: {risk_profile}
- Time horizon: {horizon}

RULES FOR YOUR RESPONSE:
1. NO jargon. Replace every technical term with plain words.
2. Use Rs amounts, not percentages where possible.
3. Help them UNDERSTAND what the data shows so they can do their own research and make their own decision.
4. Use analogies from everyday Indian life (cricket, chai, farming, etc.)
5. Make the analysis feel real and honest — not hype, not fear.
6. Warn about risks in simple terms — not scary, just honest.
7. Do NOT tell them to buy or sell anything. Do NOT mention specific share counts or prices to buy at.
8. Maximum 3rd standard reading level.

JARGON TRANSLATION GUIDE:
- "ATR" -> "How much this stock normally moves in a day"
- "Bullish Engulfing" -> "Yesterday sellers were winning, today buyers came back strongly"
- "Resistance level" -> "A price wall where sellers tend to push back"
- "Support level" -> "A price floor where buyers tend to step in"
- "Volatility" -> "How jumpy/nervous the market is right now"
- "FII outflows" -> "Big foreign investors pulling money out of India"
- "NIM compression" -> "Banks earning less profit on loans"

Return ONLY valid JSON:
{{
  "company_card": {{
    "company_name": "ONGC",
    "what_they_do": "One sentence — what this company actually does in plain words",
    "why_in_the_news": "2-3 sentences in simple language — what is happening with this company and its sector right now",
    "the_situation": "Explain the market situation like you are telling a friend over chai"
  }},
  "what_the_data_shows": {{
    "key_numbers": "The most important real numbers from the data provided — price, PE, analyst ratings, etc. ONLY numbers from the data, never invented.",
    "what_analysts_think": "What professional analysts are saying about this company (from provided data)",
    "management_signals": "What the company management has been saying recently (from provided data)"
  }},
  "things_to_research": [
    "Go to Screener.in and look up this company — check their quarterly profits for the last 4 quarters",
    "Check what analysts are saying on Trendlyne.com",
    "Read the latest quarterly results on BSE India website"
  ],
  "risk_awareness": [
    "Simple honest risk 1 — in plain language",
    "Simple honest risk 2"
  ],
  "market_mood": {{
    "current_mood": "Nervous / Calm / Excited / Fearful",
    "what_it_means": "Plain language explanation of what this mood means for regular people",
    "simple_analogy": "Market is like a cricket match where... (complete the analogy)"
  }},
  "confidence_in_analysis": {{
    "score": "7 out of 10",
    "plain_explanation": "How confident we are in this analysis and why (2 sentences max)",
    "what_could_change": "One honest sentence about what could make this analysis wrong"
  }},
  "time_context": {{
    "signal_duration": "How long this market situation is likely to last",
    "when_to_reassess": "When to come back and look at the data again",
    "patience_note": "A simple note about not panicking over daily ups and downs"
  }},
  "important_reminder": "This analysis is for learning and understanding only. It is NOT advice to buy or sell. Always do your own research or talk to a SEBI-registered advisor before putting your money anywhere."
}}
"""

PORTFOLIO_SUMMARY_PROMPT = """You are explaining a market analysis to someone who has never invested before.
They have Rs {amount} they are thinking about investing and want to understand what is happening.

COMPLETE ANALYSIS:
{recommendation}

ROOT CAUSE CONTEXT (use this to explain WHY things are happening — e.g., "Oil prices went up because OPEC cut production"):
{causal_chain_context}

Write this like you are their trusted elder brother/sister explaining what is happening in the market.
Simple, caring, honest. Do NOT tell them what to buy or sell — help them understand so THEY can decide.

Return ONLY valid JSON:
{{
  "greeting": "Personal, warm opening — acknowledge their situation",
  "situation_summary": "In 2-3 sentences — what is happening in the market right now in simple words",
  "what_we_found": {{
    "sectors_showing_strength": ["Sector 1 — why in simple words", "Sector 2 — why"],
    "sectors_showing_caution": ["Sector 1 — why to be careful"],
    "key_signals": ["The main thing driving the market right now in plain words"]
  }},
  "things_to_explore": [
    {{
      "area": "Oil & Gas companies",
      "why_interesting": "Because oil prices went up due to... (simple explanation)",
      "what_to_look_into": "Check companies like ONGC, Oil India on Screener.in — look at their recent quarterly profits"
    }}
  ],
  "general_wisdom": [
    "Never invest money you might need in the next 6 months",
    "Spreading money across different sectors is safer than putting it all in one place",
    "If you are new to investing, index funds (like Nifty 50 ETF) are the simplest way to start"
  ],
  "next_steps": [
    "Research step 1 — what to look up and where",
    "Research step 2 — what to compare"
  ],
  "monthly_check": "Once a month, check if the signals we discussed are still active — if oil prices drop back, the analysis changes",
  "reminder": "This is educational analysis only — not investment advice. Talk to a SEBI-registered advisor before investing. Never invest money you cannot afford to lose."
}}
"""


class PlainLanguageFormatter:
    """
    Translates all technical and fundamental analysis into
    language that any Indian retail investor can understand.

    The Rickshaw Driver Test:
    "If someone who saved Rs 50,000 reads this — do they understand
    what is happening and know what to research next?"
    """

    async def format_stock_recommendation(
        self,
        technical_data: dict,
        fundamental_data: dict,
        amount: float = 100000,
        risk_profile: str = "moderate",
        horizon: str = "1 year",
        causal_chain: dict = None,
    ) -> dict:
        """
        Takes complex technical + fundamental data and returns
        plain language analysis that anyone can understand.
        """
        log = logger.bind(symbol=technical_data.get("symbol"))
        log.info("plain_formatter.format_stock")

        # Format causal chain context for the prompt
        chain_ctx = "No root cause data available."
        if causal_chain:
            narrative = causal_chain.get("root_cause_narrative", "")
            root_causes = causal_chain.get("root_causes", [])
            if narrative:
                chain_ctx = narrative
            elif root_causes:
                chain_ctx = json.dumps(root_causes[:3], indent=2)

        prompt = PLAIN_LANGUAGE_PROMPT.format(
            technical_data=json.dumps({
                "symbol":       technical_data.get("symbol"),
                "price":        technical_data.get("current_price"),
                "patterns":     technical_data.get("daily_patterns", {}).get("patterns", []),
                "trend":        technical_data.get("daily_patterns", {}).get("overall_signal"),
                "trade_plan":   technical_data.get("trade_plan", {}),
                "synthesis":    technical_data.get("synthesis", {}),
                "volatility":   technical_data.get("volatility", {}).get("volatility_summary"),
                "vix_regime":   technical_data.get("volatility", {}).get("vix_regime", {}).get("label"),
            }, indent=2)[:2000],
            fundamental_data=json.dumps({
                "why_relevant":      fundamental_data.get("why_relevant", fundamental_data.get("why_chosen", [])),
                "sector":            fundamental_data.get("sector", ""),
                "signal_alignment":  fundamental_data.get("signal_alignment", ""),
                "risk_level":        fundamental_data.get("risk_level", ""),
                "data_highlights":   fundamental_data.get("data_highlights", {}),
                "risk_factors":      fundamental_data.get("risk_factors", []),
            }, indent=2)[:1000],
            causal_chain_context=chain_ctx,
            amount=f"{amount:,.0f}",
            risk_profile=risk_profile,
            horizon=horizon,
        )

        try:
            text   = await call_llm(prompt, agent_name="plain_language_formatter")
            result = json.loads(text)
            log.info("plain_formatter.complete")
            return result
        except Exception as e:
            log.warning("plain_formatter.error", error=str(e))
            return self._get_fallback_format(technical_data, amount)

    async def format_full_portfolio(
        self,
        full_recommendation: dict,
        amount: float = 100000,
        causal_chain: dict = None,
    ) -> dict:
        """
        Format the complete analysis in plain language.
        Called at the end of the main orchestrator pipeline.
        """
        log = logger.bind(amount=amount)
        log.info("plain_formatter.format_portfolio")

        company_picks = full_recommendation.get("company_picks", [])
        macro_summary = full_recommendation.get("global_macro_summary", "")
        confidence    = full_recommendation.get("confidence_score",
                        full_recommendation.get("analysis_confidence", 0.7))

        simplified = {
            "market_situation":   macro_summary,
            "overall_confidence": f"{int(confidence * 100)}%",
            "top_picks": [
                {
                    "company": pick.get("name"),
                    "sector":  pick.get("sector"),
                    "reason":  (pick.get("why_relevant") or pick.get("why_chosen", [""]))[0]
                               if (pick.get("why_relevant") or pick.get("why_chosen"))
                               else "",
                }
                for sector in company_picks
                for pick in sector.get("companies", [])[:2]
            ][:4],
            "risks":          full_recommendation.get("what_could_go_wrong", [])[:3],
            "tax_education":  full_recommendation.get("tax_optimizations", [{}])[0]
                              if full_recommendation.get("tax_optimizations") else {},
        }

        # Format causal chain context
        chain_ctx = "No root cause data available."
        if causal_chain:
            narrative = causal_chain.get("root_cause_narrative", "")
            root_causes = causal_chain.get("root_causes", [])
            if narrative:
                chain_ctx = narrative
            elif root_causes:
                chain_ctx = json.dumps(root_causes[:3], indent=2)

        prompt = PORTFOLIO_SUMMARY_PROMPT.format(
            amount=f"{amount:,.0f}",
            recommendation=json.dumps(simplified, indent=2)[:3000],
            causal_chain_context=chain_ctx,
        )

        try:
            text   = await call_llm(prompt, agent_name="plain_language_formatter")
            result = json.loads(text)
            log.info("plain_formatter.portfolio_complete")
            return result
        except Exception as e:
            log.warning("plain_formatter.portfolio_error", error=str(e))
            return {
                "situation_summary": macro_summary,
                "error": "Could not generate plain language summary",
            }

    def _get_fallback_format(self, technical_data: dict, amount: float) -> dict:
        """Simple fallback if LLM formatting fails."""
        symbol = technical_data.get("symbol", "Stock")

        return {
            "company_card": {
                "company_name": symbol,
                "why_in_the_news": "Our system identified this company as relevant to current market signals.",
                "the_situation": "We could not fully load the analysis. Please check back later.",
            },
            "things_to_research": [
                f"Look up {symbol} on Screener.in to see their recent quarterly results",
                f"Check analyst ratings for {symbol} on Trendlyne.com",
                "Review the latest quarterly results on the BSE India website",
                "Compare with other companies in the same sector",
            ],
            "risk_awareness": [
                "Markets can go up or down — never invest money you need in the next 6 months",
                "Do your own research before making any investment decision",
            ],
            "important_reminder": (
                "This is educational analysis only — not investment advice. "
                "Talk to a SEBI-registered advisor before investing."
            ),
        }
