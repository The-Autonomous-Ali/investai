"""
Plain Language Formatter — Translates technical analysis into simple language.

Mission: A person with zero financial background should be able to read
this output and know EXACTLY what to do, when to do it, and why.

The "Rickshaw Driver Test": If someone who has saved ₹50,000 reads this,
will they know exactly what to do tomorrow morning? If not — simplify more.
"""
import json
import structlog
from utils.llm_client import call_llm

logger = structlog.get_logger()

PLAIN_LANGUAGE_PROMPT = """You are translating a complex investment recommendation into simple language
that ANY Indian person — even with zero financial background — can understand and act on.

TECHNICAL RECOMMENDATION:
{technical_data}

FUNDAMENTAL DATA:
{fundamental_data}

USER PROFILE:
- Investment amount: ₹{amount}
- Risk tolerance: {risk_profile}
- Time horizon: {horizon}

RULES FOR YOUR RESPONSE:
1. NO jargon. Replace every technical term with plain words.
2. Use ₹ amounts, not percentages where possible.
3. Tell them EXACTLY what to do — not options, one clear action.
4. Use analogies from everyday Indian life (cricket, chai, farming, etc.)
5. The stop loss should sound like protection, not failure.
6. Make the opportunity feel real and exciting but honest.
7. Warn about risks in simple terms — not scary, just honest.
8. Maximum 3rd standard reading level.

JARGON TRANSLATION GUIDE:
- "Stop loss" → "Safety net price — below this, sell and walk away"
- "ATR" → "How much this stock normally moves in a day"
- "Bullish Engulfing" → "Yesterday sellers were winning, today buyers came back strongly"
- "Resistance level" → "A price wall where sellers tend to push back"
- "Support level" → "A price floor where buyers tend to step in"
- "Risk:Reward 1:3" → "For every ₹100 you risk losing, you could gain ₹300"
- "Volatility" → "How jumpy/nervous the market is right now"
- "FII outflows" → "Big foreign investors pulling money out of India"
- "NIM compression" → "Banks earning less profit on loans"
- "Portfolio allocation" → "How to split your money"

Return ONLY valid JSON:
{{
  "stock_card": {{
    "company_name": "ONGC",
    "what_they_do": "One sentence — what this company actually does in plain words",
    "why_buy_now": "2-3 sentences in simple language — why NOW is a good time",
    "the_opportunity": "Explain the market situation like you're telling a friend over chai"
  }},
  "action_plan": {{
    "what_to_do": "Buy / Sell / Wait — one clear word",
    "how_much_to_invest": "₹X out of your ₹Y savings",
    "how_many_shares": "Buy X shares",
    "when_to_buy": "Buy this week / Wait for price to drop to ₹X / Buy immediately",
    "buy_in_two_parts": true,
    "part_1": "Buy X shares now at around ₹X",
    "part_2": "Buy remaining X shares if price drops to ₹X"
  }},
  "money_plan": {{
    "your_investment": "₹X",
    "if_it_goes_well": "After 45-70 days, your ₹X could become ₹Y (you gain ₹Z)",
    "if_it_goes_wrong": "Worst case, you lose ₹X (that is X% of your investment)",
    "your_safety_net": "If price falls to ₹X — sell immediately. Do not wait. Do not hope.",
    "safety_net_in_rupees": "You would lose maximum ₹X out of your ₹Y investment"
  }},
  "when_to_sell": {{
    "good_news_sell": "When price reaches ₹X, sell half your shares and enjoy the profit",
    "great_news_sell": "When price reaches ₹Y, sell all remaining shares",
    "bad_news_sell": "If price falls below ₹Z — sell everything immediately, no waiting",
    "warning_sign": "One simple thing to watch that tells you the story has changed"
  }},
  "simple_checklist": [
    "✅ Step 1: Open your Zerodha/Groww app",
    "✅ Step 2: Search for ONGC",
    "✅ Step 3: Buy X shares at market price",
    "✅ Step 4: Set a price alert at ₹X (your safety net)",
    "✅ Step 5: Set a price alert at ₹Y (your profit target)",
    "✅ Step 6: Check back in 2 weeks — don't panic if it goes up or down a little"
  ],
  "honest_risks": [
    "Simple honest risk 1 — in plain language",
    "Simple honest risk 2"
  ],
  "market_mood": {{
    "current_mood": "Nervous / Calm / Excited / Fearful",
    "what_it_means_for_you": "Plain language explanation",
    "simple_analogy": "Market is like a cricket match where... (complete the analogy)"
  }},
  "confidence_meter": {{
    "score": "7 out of 10",
    "plain_explanation": "We are fairly confident because... (2 sentences max)",
    "what_could_go_wrong": "One honest sentence about the main risk"
  }},
  "hold_duration": {{
    "how_long": "About 45-70 days — roughly 2 months",
    "what_to_do_till_then": "Check once a week. Don't check daily — it will make you nervous for no reason.",
    "review_date": "Come back and review on [date]"
  }}
}}
"""

PORTFOLIO_SUMMARY_PROMPT = """You are explaining a complete investment plan to someone who has never invested before.
They have ₹{amount} to invest and want to grow their money safely.

COMPLETE RECOMMENDATION:
{recommendation}

Write this like you are their trusted elder brother/sister explaining what to do with their savings.
Simple, caring, honest, and actionable.

Return ONLY valid JSON:
{{
  "greeting": "Personal, warm opening — acknowledge their situation",
  "situation_summary": "In 2-3 sentences — what is happening in the market right now in simple words",
  "your_complete_plan": {{
    "total_to_invest": "₹X out of your ₹{amount}",
    "keep_in_hand": "Keep ₹Y aside — never invest everything",
    "breakdown": [
      {{
        "where": "Company/Fund name",
        "how_much": "₹X",
        "why_in_one_line": "Simple reason",
        "when_to_sell": "Simple exit condition"
      }}
    ]
  }},
  "monthly_check": "What to do once a month — specific simple actions",
  "golden_rules": [
    "Rule 1 in simple language",
    "Rule 2 in simple language",
    "Rule 3 in simple language"
  ],
  "what_success_looks_like": "In 6 months, if everything goes well... (paint a picture)",
  "what_failure_looks_like": "Worst case scenario in honest simple terms — and why it's okay",
  "one_last_thing": "One piece of honest advice from a caring friend"
}}
"""


class PlainLanguageFormatter:
    """
    Translates all technical and fundamental analysis into
    language that any Indian retail investor can understand.
    
    The Rickshaw Driver Test:
    "If someone who saved ₹50,000 reads this — do they know exactly what to do?"
    """

    async def format_stock_recommendation(
        self,
        technical_data: dict,
        fundamental_data: dict,
        amount: float = 100000,
        risk_profile: str = "moderate",
        horizon: str = "1 year",
    ) -> dict:
        """
        Takes complex technical + fundamental data and returns
        plain language that anyone can understand and act on.
        """
        log = logger.bind(symbol=technical_data.get("symbol"))
        log.info("plain_formatter.format_stock")

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
                "why_chosen":        fundamental_data.get("why_chosen", []),
                "sector":            fundamental_data.get("sector", ""),
                "signal_alignment":  fundamental_data.get("signal_alignment", ""),
                "risk_level":        fundamental_data.get("risk_level", ""),
                "entry_strategy":    fundamental_data.get("entry_strategy", ""),
                "upside_potential":  fundamental_data.get("upside_potential", ""),
            }, indent=2)[:1000],
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
    ) -> dict:
        """
        Format the complete portfolio recommendation in plain language.
        Called at the end of the main orchestrator pipeline.
        """
        log = logger.bind(amount=amount)
        log.info("plain_formatter.format_portfolio")

        # Extract key info for the prompt
        allocation   = full_recommendation.get("allocation", {})
        company_picks = full_recommendation.get("company_picks", [])
        macro_summary = full_recommendation.get("global_macro_summary", "")
        tech_analysis = full_recommendation.get("technical_analysis", [])
        confidence    = full_recommendation.get("confidence_score", 0.7)

        # Build simplified recommendation for the prompt
        simplified = {
            "market_situation":  macro_summary,
            "overall_confidence": f"{int(confidence * 100)}%",
            "allocation":        allocation,
            "top_picks":         [
                {
                    "company":  pick.get("name"),
                    "sector":   pick.get("sector"),
                    "reason":   pick.get("why_chosen", [""])[0] if pick.get("why_chosen") else "",
                    "buy_at":   pick.get("current_price_approx"),
                    "target":   pick.get("target_price_1yr"),
                }
                for sector in company_picks
                for pick in sector.get("companies", [])[:2]
            ][:4],
            "risks":             full_recommendation.get("what_could_go_wrong", [])[:3],
            "tax_saving_tip":    full_recommendation.get("tax_optimizations", [{}])[0]
                                 if full_recommendation.get("tax_optimizations") else {},
        }

        prompt = PORTFOLIO_SUMMARY_PROMPT.format(
            amount=f"{amount:,.0f}",
            recommendation=json.dumps(simplified, indent=2)[:3000],
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
        symbol     = technical_data.get("symbol", "Stock")
        price      = technical_data.get("current_price", 0)
        trade_plan = technical_data.get("trade_plan", {})
        stop_loss  = trade_plan.get("stop_loss", {}).get("price", price * 0.92)
        target1    = trade_plan.get("targets", {}).get("target1", price * 1.08)
        shares     = trade_plan.get("position_sizing", {}).get("shares", 0)

        return {
            "stock_card": {
                "company_name": symbol,
                "why_buy_now":  "Our system identified this as a good opportunity based on current market signals.",
            },
            "action_plan": {
                "what_to_do":       "Buy",
                "how_many_shares":  f"Buy {shares} shares",
                "when_to_buy":      "This week",
            },
            "money_plan": {
                "your_safety_net": f"If price falls to ₹{stop_loss:.0f} — sell immediately",
                "if_it_goes_well": f"Target: ₹{target1:.0f}",
            },
            "simple_checklist": [
                f"✅ Search for {symbol} on your trading app",
                f"✅ Buy {shares} shares at current price",
                f"✅ Set alert at ₹{stop_loss:.0f} (safety net)",
                f"✅ Set alert at ₹{target1:.0f} (profit target)",
                "✅ Check back in 2 weeks",
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE — What the output looks like
# ─────────────────────────────────────────────────────────────────────────────

EXAMPLE_OUTPUT = {
    "stock_card": {
        "company_name": "ONGC",
        "what_they_do": "India's biggest oil company — they drill oil from the ground and sell it.",
        "why_buy_now": "Oil prices jumped to $103 because of fighting in the Middle East. When oil is expensive, ONGC makes more money. It's like if the price of atta doubled — chakki owners would earn more.",
        "the_opportunity": "Imagine you own a shop that sells water, and suddenly there's a drought. Everyone needs water, prices go up, you earn more. That's ONGC right now with oil."
    },
    "action_plan": {
        "what_to_do": "Buy",
        "how_much_to_invest": "₹15,000 out of your ₹1,00,000",
        "how_many_shares": "Buy 56 shares",
        "when_to_buy": "Buy this week — don't wait too long",
        "buy_in_two_parts": True,
        "part_1": "Buy 34 shares now at around ₹265",
        "part_2": "Buy 22 more shares if price drops to ₹258"
    },
    "money_plan": {
        "your_investment": "₹15,000",
        "if_it_goes_well": "In about 2 months, your ₹15,000 could become ₹17,500 (you gain ₹2,500)",
        "if_it_goes_wrong": "Worst case, you lose ₹1,050 — that is only 1% of your total savings",
        "your_safety_net": "If price falls to ₹249 — sell immediately. Do not wait. Do not hope it comes back.",
        "safety_net_in_rupees": "You would lose maximum ₹1,050 out of your ₹1,00,000"
    },
    "when_to_sell": {
        "good_news_sell": "When price reaches ₹295, sell half your shares — take the profit and celebrate",
        "great_news_sell": "When price reaches ₹318, sell all remaining shares — well done",
        "bad_news_sell": "If price falls to ₹249 — sell everything immediately, no discussion",
        "warning_sign": "If you see news that oil prices dropped below $90 — that means the story has changed, sell"
    },
    "simple_checklist": [
        "✅ Step 1: Open your Zerodha / Groww / Upstox app",
        "✅ Step 2: Search for 'ONGC'",
        "✅ Step 3: Buy 34 shares at market price (around ₹265)",
        "✅ Step 4: Set a price ALERT at ₹249 (your safety net — sell if it reaches this)",
        "✅ Step 5: Set a price ALERT at ₹295 (sell half when it reaches this)",
        "✅ Step 6: Don't check every hour — check once a week on Sunday"
    ],
    "honest_risks": [
        "If the Middle East fighting stops suddenly, oil prices will fall and ONGC will fall too",
        "The Indian government sometimes controls oil prices — this can reduce ONGC's profits"
    ],
    "market_mood": {
        "current_mood": "Nervous",
        "what_it_means_for_you": "The market is like a nervous cricket crowd right now — any bad news and everyone panics. That's why we're investing only ₹15,000 and not more.",
        "simple_analogy": "Market is like a cricket match where India is batting in a tense finish. Good balls and bad balls will both come — stay calm and watch the big picture."
    },
    "confidence_meter": {
        "score": "7.5 out of 10",
        "plain_explanation": "We are fairly confident because both the news (oil prices) and the stock chart (Hammer pattern) are saying the same thing — buy. When two different signals agree, we trust it more.",
        "what_could_go_wrong": "If peace suddenly comes in the Middle East and oil prices crash — sell immediately."
    },
    "hold_duration": {
        "how_long": "About 45-70 days — roughly 2 months",
        "what_to_do_till_then": "Check once every Sunday. If nothing dramatic happens in the news, just hold. Don't sell because of small ups and downs.",
        "review_date": "Come back and review on May 1, 2026"
    }
}