"""
Company Intelligence Agent — The Stock Picker.

Once sectors are identified, this agent:
1. Finds top performing companies in those sectors
2. Explains WHY each was chosen (fundamentals + signal fit)
3. Surfaces hidden gems / emerging companies
4. Scores each company against the current signal environment
5. Provides entry guidance for each pick
"""
import json
import structlog
from anthropic import AsyncAnthropic
from datetime import datetime

logger = structlog.get_logger()
client = AsyncAnthropic()

# ─── Prompts ──────────────────────────────────────────────────────────────────

COMPANY_PICKER_PROMPT = """You are a senior equity research analyst specializing in Indian markets (NSE/BSE).

Your job is to identify the BEST specific companies to invest in, given the current market signals and identified sectors.

CURRENT SIGNALS: {signals}
SECTORS TO BUY: {sectors_to_buy}
SECTORS TO AVOID: {sectors_to_avoid}
INVESTMENT AMOUNT: ₹{amount}
TIME HORIZON: {horizon}
USER RISK PROFILE: {risk_profile}

For each sector to buy, identify:
1. The TOP 2-3 established companies (proven track record)
2. 1 EMERGING company (newer, higher risk but higher potential)
3. The BEST ETF/INDEX FUND option for that sector (safer alternative)

For EACH company provide a full research brief.

Return ONLY valid JSON:
{{
  "sector_picks": [
    {{
      "sector": "Oil & Gas",
      "signal_fit_score": 9.2,
      "signal_fit_reason": "Direct beneficiary of oil price spike. Every $10 rise in Brent adds ~₹2000 crore to ONGC's EBITDA.",
      "companies": [
        {{
          "name": "ONGC",
          "nse_symbol": "ONGC",
          "type": "established",
          "category": "large_cap",
          "why_chosen": [
            "India's largest oil producer — direct oil price beneficiary",
            "Every $1 rise in Brent = ~₹400 crore additional profit",
            "Government backing reduces bankruptcy risk",
            "Current valuation at 6x P/E — historically cheap"
          ],
          "current_price_approx": "₹265",
          "target_price_1yr": "₹320",
          "upside_potential": "20%",
          "risk_level": "medium",
          "key_risk": "Government may cap fuel prices, limiting upside",
          "signal_alignment": "high",
          "fundamentals": {{
            "pe_ratio": "6.2x",
            "debt_to_equity": "0.3x",
            "revenue_growth_3yr": "18%",
            "dividend_yield": "4.2%"
          }},
          "best_for": "moderate risk investors wanting oil exposure with safety",
          "investment_mode": "lumpsum or SIP both work",
          "entry_strategy": "Buy in 2 tranches — 60% now, 40% on any 5% dip"
        }},
        {{
          "name": "Oil India Ltd",
          "nse_symbol": "OIL",
          "type": "established",
          "category": "mid_cap",
          "why_chosen": [
            "Smaller than ONGC but growing faster",
            "Northeast India gas fields are undervalued asset",
            "Dividend yield of 5.8% provides income floor"
          ],
          "current_price_approx": "₹580",
          "target_price_1yr": "₹720",
          "upside_potential": "24%",
          "risk_level": "medium",
          "key_risk": "Lower liquidity than ONGC — harder to exit quickly",
          "signal_alignment": "high",
          "fundamentals": {{
            "pe_ratio": "8.1x",
            "debt_to_equity": "0.4x",
            "revenue_growth_3yr": "22%",
            "dividend_yield": "5.8%"
          }},
          "best_for": "investors comfortable with mid-cap, want higher growth",
          "investment_mode": "lumpsum preferred",
          "entry_strategy": "Single tranche buy — liquidity risk means don't average down too aggressively"
        }},
        {{
          "name": "Chemcrux Enterprises",
          "nse_symbol": "CHEMCRUX",
          "type": "emerging",
          "category": "small_cap",
          "why_chosen": [
            "Specialty chemicals company pivoting to oil & gas chemical supply",
            "Revenue up 140% in last 2 years",
            "Under-researched — only 2 analyst reports exist",
            "Major capex expansion aligned with oil sector growth"
          ],
          "current_price_approx": "₹340",
          "target_price_1yr": "₹520",
          "upside_potential": "53%",
          "risk_level": "high",
          "key_risk": "Small cap illiquidity + limited analyst coverage = high volatility",
          "signal_alignment": "medium",
          "fundamentals": {{
            "pe_ratio": "18x",
            "debt_to_equity": "0.8x",
            "revenue_growth_3yr": "68%",
            "dividend_yield": "0.5%"
          }},
          "best_for": "aggressive investors willing to hold 2+ years",
          "investment_mode": "small SIP only — max 5% of portfolio",
          "entry_strategy": "SIP over 4 months — never put more than 5% of portfolio here"
        }}
      ],
      "etf_alternative": {{
        "name": "Nippon India ETF Nifty CPSE ETF",
        "symbol": "CPSEETF",
        "why_chosen": "Captures ONGC, Coal India, Power Finance — all oil/energy PSUs in one safe instrument",
        "expense_ratio": "0.01%",
        "best_for": "beginners or risk-averse investors who want sector exposure without stock picking"
      }}
    }}
  ],
  "portfolio_construction_note": "Across all sector picks, never put more than 20% in a single company and never more than 5% in any single small cap.",
  "total_stocks_suggested": 8,
  "diversification_score": 7.5
}}
"""

INVESTMENT_MANAGER_PROMPT = """You are a senior Investment Manager with 20 years of experience managing Indian retail investor portfolios.

Your job is to build a COMPLETE INVESTMENT STRATEGY — not just what to buy, but exactly HOW to invest, WHEN to invest, HOW MUCH at each step, and WHEN to exit.

USER SITUATION:
- Total Amount: ₹{amount}
- Time Horizon: {horizon}
- Risk Profile: {risk_profile}
- Monthly Income Estimate: {monthly_income}
- Current Holdings: {existing_holdings}

RECOMMENDED COMPANIES: {company_picks}
MARKET SIGNALS: {signals_summary}
TEMPORAL OUTLOOK: {temporal_outlook}
TAX BRACKET: {tax_bracket}%

BUILD A COMPLETE INVESTMENT PLAYBOOK:

Return ONLY valid JSON:
{{
  "strategy_name": "Defensive Growth Strategy — Oil Cycle + IT Currency Play",
  "strategy_rationale": "2-3 paragraph explanation of the overall strategy thesis",
  
  "deployment_plan": {{
    "approach": "phased",
    "reasoning": "Market uncertainty from geopolitical signals — don't invest all at once",
    "phases": [
      {{
        "phase": 1,
        "label": "Immediate Deployment",
        "timing": "This week",
        "amount": 50000,
        "percentage_of_total": 50,
        "what_to_buy": [
          {{"instrument": "ONGC", "amount": 20000, "reason": "High conviction, oil signal peaking"}},
          {{"instrument": "Nifty 50 Index Fund", "amount": 20000, "reason": "Core allocation, always buy early"}},
          {{"instrument": "Liquid Fund", "amount": 10000, "reason": "Keep dry powder for phase 2"}}
        ],
        "trigger": "Deploy immediately — don't wait"
      }},
      {{
        "phase": 2,
        "label": "Opportunistic Buy",
        "timing": "If Nifty corrects 3-5% from current levels, or in 3 weeks whichever comes first",
        "amount": 30000,
        "percentage_of_total": 30,
        "what_to_buy": [
          {{"instrument": "Gold ETF / SGB", "amount": 20000, "reason": "Inflation hedge, better entry after any dollar strengthening"}},
          {{"instrument": "IT Sector Fund", "amount": 10000, "reason": "INR depreciation benefits IT"}}
        ],
        "trigger": "Nifty below 21800 OR 3 weeks elapsed"
      }},
      {{
        "phase": 3,
        "label": "Reserve & Rebalance",
        "timing": "Month 2-3",
        "amount": 20000,
        "percentage_of_total": 20,
        "what_to_buy": [
          {{"instrument": "Review and top-up best performers", "amount": 20000, "reason": "Add to winners, not losers"}}
        ],
        "trigger": "After first review at 8 weeks"
      }}
    ]
  }},
  
  "sip_vs_lumpsum": {{
    "recommendation": "phased_lumpsum",
    "reasoning": "SIP is best for long-term equity wealth building (5+ years). For 1 year with specific signal-based thesis, phased lumpsum beats SIP.",
    "if_sip_preferred": {{
      "monthly_amount": 8500,
      "duration_months": 12,
      "instruments": [
        {{"name": "Nifty 50 Index Fund", "monthly": 4000}},
        {{"name": "Gold ETF", "monthly": 2500}},
        {{"name": "Liquid Fund", "monthly": 2000}}
      ],
      "note": "If market falls >10%, increase SIP by 50% for that month (buy more on dips)"
    }}
  }},
  
  "rebalancing_schedule": [
    {{
      "at": "8 weeks",
      "action": "First review — check if signals have changed",
      "what_to_check": ["Brent crude price vs $95 threshold", "INR vs 84.5 level", "FII flows trend"],
      "if_signals_unchanged": "Hold all positions",
      "if_de_escalation": "Start reducing ONGC from 15% to 8%"
    }},
    {{
      "at": "6 months",
      "action": "Major rebalancing checkpoint",
      "what_to_check": ["Portfolio performance vs Nifty", "Original signal still active?", "Tax implications"],
      "rebalance_rule": "Trim any position that has grown to >25% of portfolio. Add to laggards only if thesis unchanged."
    }}
  ],
  
  "exit_strategy": {{
    "planned_exit": {{
      "date": "12 months from today",
      "method": "Gradual — sell 25% per month over final 4 months to avoid timing risk",
      "tax_note": "Hold equity >12 months for LTCG benefit at 10% vs STCG at 15%"
    }},
    "emergency_exits": [
      {{
        "trigger": "Portfolio falls more than 15% from peak",
        "action": "Exit small caps immediately, reduce equity to 30%, shift to liquid funds",
        "reason": "Capital preservation over returns"
      }},
      {{
        "trigger": "Iran-Israel conflict fully de-escalates (ceasefire confirmed)",
        "action": "Sell ONGC within 48 hours — oil will reverse fast",
        "reason": "The core thesis for holding ONGC disappears instantly"
      }},
      {{
        "trigger": "India VIX crosses 22",
        "action": "Sell 30% of equity holdings, move to liquid/gold",
        "reason": "Systemic fear entering market — protect capital"
      }}
    ],
    "profit_booking": [
      {{
        "trigger": "Any single stock up 30% in < 3 months",
        "action": "Book 50% profit — let the rest run",
        "reason": "Capture gains while staying in for further upside"
      }}
    ]
  }},
  
  "monthly_monitoring": {{
    "weekly_checks": ["India VIX level", "Brent crude price", "FII/DII daily flows"],
    "monthly_checks": ["Portfolio vs Nifty performance", "Signal status update", "Tax position"],
    "dont_check_daily": "Avoid checking your portfolio price every day — it leads to emotional decisions"
  }},
  
  "behavioral_guardrails": [
    "Never add more than planned if a stock is falling — only add if the THESIS is unchanged",
    "Never sell in panic on a single bad news day — check if the core signal has changed first",
    "Set price alerts for exit triggers — don't rely on memory",
    "Don't add new stocks outside this plan without running the full analysis again"
  ],
  
  "expected_outcome": {{
    "base_case_return": "12-16%",
    "best_case_return": "22-28%",
    "worst_case_return": "-8% to -12%",
    "probability_of_positive_return": "71%",
    "vs_fixed_deposit": "FD gives ~7% — this targets 12-16% with higher risk",
    "vs_nifty": "Strategy targets Nifty +4-6% outperformance if oil thesis plays out"
  }},
  
  "manager_note": "One honest note: this strategy is built on the oil/geopolitical signal. If that signal reverses (ceasefire, OPEC supply increase), you must act on the exit triggers. The biggest mistake investors make is staying in a position after the original thesis has changed."
}}
"""

# ─── Company Data Layer ───────────────────────────────────────────────────────

# Fallback company database when live data is unavailable
# In production this would be populated from NSE API + screener.in
COMPANY_DB = {
    "Oil & Gas": {
        "established": [
            {"name": "ONGC",      "symbol": "ONGC",      "cap": "large", "pe": 6.2,  "div_yield": 4.2, "revenue_growth": 18},
            {"name": "Oil India", "symbol": "OIL",       "cap": "mid",   "pe": 8.1,  "div_yield": 5.8, "revenue_growth": 22},
            {"name": "Reliance",  "symbol": "RELIANCE",  "cap": "large", "pe": 24.0, "div_yield": 0.4, "revenue_growth": 12},
        ],
        "emerging": [
            {"name": "Selan Exploration", "symbol": "SELAN", "cap": "small", "pe": 15.0, "revenue_growth": 45},
        ],
        "etf": {"name": "CPSE ETF", "symbol": "CPSEETF", "expense_ratio": 0.01},
    },
    "IT": {
        "established": [
            {"name": "TCS",       "symbol": "TCS",       "cap": "large", "pe": 28.0, "div_yield": 1.5, "revenue_growth": 14},
            {"name": "Infosys",   "symbol": "INFY",      "cap": "large", "pe": 24.0, "div_yield": 2.8, "revenue_growth": 11},
            {"name": "HCL Tech",  "symbol": "HCLTECH",   "cap": "large", "pe": 20.0, "div_yield": 4.1, "revenue_growth": 17},
        ],
        "emerging": [
            {"name": "Newgen Software", "symbol": "NEWGEN", "cap": "mid", "pe": 38.0, "revenue_growth": 32},
        ],
        "etf": {"name": "Nifty IT ETF", "symbol": "ITBEES", "expense_ratio": 0.15},
    },
    "Banking": {
        "established": [
            {"name": "HDFC Bank",  "symbol": "HDFCBANK", "cap": "large", "pe": 17.0, "div_yield": 1.2, "revenue_growth": 19},
            {"name": "ICICI Bank", "symbol": "ICICIBANK", "cap": "large", "pe": 16.5, "div_yield": 0.9, "revenue_growth": 23},
            {"name": "Kotak Bank", "symbol": "KOTAKBANK", "cap": "large", "pe": 18.0, "div_yield": 0.1, "revenue_growth": 18},
        ],
        "emerging": [
            {"name": "Ujjivan SFB", "symbol": "UJJIVANSFB", "cap": "small", "pe": 9.0, "revenue_growth": 41},
        ],
        "etf": {"name": "Bank Nifty ETF", "symbol": "BANKBEES", "expense_ratio": 0.17},
    },
    "Gold": {
        "established": [
            {"name": "Sovereign Gold Bond 2029", "symbol": "SGBMAR29", "cap": "n/a", "pe": None, "div_yield": 2.5, "revenue_growth": 0},
            {"name": "Nippon Gold ETF",          "symbol": "GOLDBEES", "cap": "n/a", "pe": None, "div_yield": 0,   "revenue_growth": 0},
        ],
        "emerging": [],
        "etf": {"name": "Nippon Gold ETF", "symbol": "GOLDBEES", "expense_ratio": 0.54},
    },
    "Infrastructure": {
        "established": [
            {"name": "L&T",         "symbol": "LT",         "cap": "large", "pe": 31.0, "div_yield": 0.8, "revenue_growth": 16},
            {"name": "Power Grid",  "symbol": "POWERGRID",  "cap": "large", "pe": 16.0, "div_yield": 4.5, "revenue_growth": 8},
            {"name": "IRFC",        "symbol": "IRFC",       "cap": "large", "pe": 29.0, "div_yield": 1.2, "revenue_growth": 25},
        ],
        "emerging": [
            {"name": "KPI Green Energy", "symbol": "KPIGREEN", "cap": "small", "pe": 35.0, "revenue_growth": 110},
        ],
        "etf": {"name": "Nifty Infra ETF", "symbol": "INFRABEES", "expense_ratio": 0.20},
    },
    "Pharma": {
        "established": [
            {"name": "Sun Pharma",   "symbol": "SUNPHARMA", "cap": "large", "pe": 34.0, "div_yield": 0.8, "revenue_growth": 14},
            {"name": "Dr. Reddy's", "symbol": "DRREDDY",   "cap": "large", "pe": 22.0, "div_yield": 0.7, "revenue_growth": 18},
            {"name": "Cipla",        "symbol": "CIPLA",     "cap": "large", "pe": 25.0, "div_yield": 0.6, "revenue_growth": 13},
        ],
        "emerging": [
            {"name": "Gland Pharma", "symbol": "GLAND", "cap": "mid", "pe": 30.0, "revenue_growth": 28},
        ],
        "etf": {"name": "Pharma ETF", "symbol": "PHARMABEES", "expense_ratio": 0.18},
    },
    "Defence": {
        "established": [
            {"name": "HAL",  "symbol": "HAL",  "cap": "large", "pe": 38.0, "div_yield": 0.5, "revenue_growth": 22},
            {"name": "BEL",  "symbol": "BEL",  "cap": "large", "pe": 40.0, "div_yield": 0.8, "revenue_growth": 18},
            {"name": "BHEL", "symbol": "BHEL", "cap": "large", "pe": 90.0, "div_yield": 0.3, "revenue_growth": 32},
        ],
        "emerging": [
            {"name": "Data Patterns",  "symbol": "DATAPATTNS", "cap": "small", "pe": 65.0, "revenue_growth": 48},
        ],
        "etf": {"name": "Mirae India Defence ETF", "symbol": "MIDEFTF", "expense_ratio": 0.35},
    },
    "Renewable Energy": {
        "established": [
            {"name": "Adani Green",  "symbol": "ADANIGREEN",  "cap": "large", "pe": 120.0, "div_yield": 0.0, "revenue_growth": 42},
            {"name": "Tata Power",   "symbol": "TATAPOWER",   "cap": "large", "pe": 40.0,  "div_yield": 0.4, "revenue_growth": 25},
            {"name": "NTPC Green",   "symbol": "NTPCGREEN",   "cap": "large", "pe": 85.0,  "div_yield": 0.2, "revenue_growth": 38},
        ],
        "emerging": [
            {"name": "Waaree Energies", "symbol": "WAAREE", "cap": "mid", "pe": 45.0, "revenue_growth": 78},
        ],
        "etf": {"name": "Mirae Nifty India Manufacturing ETF", "symbol": "MFGE", "expense_ratio": 0.30},
    },
}


class CompanyIntelligenceAgent:
    """
    Finds the best specific companies to invest in within identified sectors.
    Also surfaces emerging companies with high growth potential.
    """

    def __init__(self, db_session=None):
        self.db = db_session

    async def analyze(self, inputs: dict) -> dict:
        """
        Main entry point.
        Takes sectors_to_buy from research agent and returns specific company picks.
        """
        sectors_to_buy   = inputs.get("sectors_to_buy", [])
        sectors_to_avoid = inputs.get("sectors_to_avoid", [])
        amount           = inputs.get("amount", 100000)
        horizon          = inputs.get("horizon", "1 year")
        risk_profile     = inputs.get("user_profile", {}).get("risk_tolerance", "moderate")
        signals          = inputs.get("signal_watcher", {}).get("signals", [])

        if not sectors_to_buy:
            return {"sector_picks": [], "error": "no_sectors_identified"}

        log = logger.bind(sectors=len(sectors_to_buy))
        log.info("company_intelligence.start")

        # Enrich with company DB data
        enriched_sectors = self._enrich_sectors(sectors_to_buy)

        # Run AI analysis for company picks
        result = await self._run_company_analysis(
            signals=signals,
            sectors_to_buy=enriched_sectors,
            sectors_to_avoid=sectors_to_avoid,
            amount=amount,
            horizon=horizon,
            risk_profile=risk_profile,
        )

        log.info("company_intelligence.complete", picks=len(result.get("sector_picks", [])))
        return result

    def _enrich_sectors(self, sectors_to_buy: list) -> list:
        """Add known company data to sector list."""
        enriched = []
        for sector_item in sectors_to_buy:
            sector_name = sector_item.get("sector", "") if isinstance(sector_item, dict) else sector_item
            db_data = COMPANY_DB.get(sector_name, {})
            enriched.append({
                "sector":      sector_name,
                "reason":      sector_item.get("reason", "") if isinstance(sector_item, dict) else "",
                "instruments": sector_item.get("instruments", []) if isinstance(sector_item, dict) else [],
                "known_companies": {
                    "established": db_data.get("established", []),
                    "emerging":    db_data.get("emerging", []),
                    "etf":         db_data.get("etf", {}),
                }
            })
        return enriched

    async def _run_company_analysis(
        self,
        signals: list,
        sectors_to_buy: list,
        sectors_to_avoid: list,
        amount: float,
        horizon: str,
        risk_profile: str,
    ) -> dict:
        signals_summary = [
            {"title": s.get("title"), "type": s.get("signal_type"), "importance": s.get("importance_score")}
            for s in signals[:5]
        ]

        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": COMPANY_PICKER_PROMPT.format(
                    signals=json.dumps(signals_summary, indent=2),
                    sectors_to_buy=json.dumps(sectors_to_buy, indent=2),
                    sectors_to_avoid=json.dumps(sectors_to_avoid, indent=2),
                    amount=f"{amount:,.0f}",
                    horizon=horizon,
                    risk_profile=risk_profile,
                )
            }]
        )

        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)


class InvestmentManagerAgent:
    """
    Acts as a full Investment Manager.
    Builds complete strategy: HOW to invest, HOW MUCH, WHEN, and WHEN to exit.
    Wraps all other agents' outputs into a single actionable playbook.
    """

    def __init__(self, db_session=None):
        self.db = db_session

    async def build_strategy(self, inputs: dict) -> dict:
        """
        Synthesizes all agent outputs into a complete investment playbook.
        This is the FINAL output the user sees after all other agents have run.
        """
        company_picks  = inputs.get("company_intelligence", {})
        signals        = inputs.get("signal_watcher", {}).get("signals", [])
        temporal       = inputs.get("temporal_agent", {})
        user_profile   = inputs.get("user_profile", {})
        amount         = inputs.get("amount", 100000)
        horizon        = inputs.get("horizon", "1 year")

        log = logger.bind(amount=amount, horizon=horizon)
        log.info("investment_manager.start")

        signals_summary = "\n".join([
            f"- {s.get('title', '')} (importance: {s.get('importance_score', 0)}/10)"
            for s in signals[:5]
        ])

        temporal_outlook = (
            temporal.get("overall_market_phase", "neutral") + " — " +
            "; ".join([
                f"{t.get('signal_title', '')}: {t.get('lifecycle_stage', '')} ({t.get('duration_type', '')})"
                for t in temporal.get("timelines", [])[:3]
            ])
        )

        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": INVESTMENT_MANAGER_PROMPT.format(
                    amount=f"{amount:,.0f}",
                    horizon=horizon,
                    risk_profile=user_profile.get("risk_tolerance", "moderate"),
                    monthly_income=user_profile.get("monthly_income_bracket", "unknown"),
                    existing_holdings=json.dumps(user_profile.get("current_holdings", []), indent=2),
                    company_picks=json.dumps(company_picks.get("sector_picks", [])[:3], indent=2)[:2000],
                    signals_summary=signals_summary,
                    temporal_outlook=temporal_outlook,
                    tax_bracket=user_profile.get("tax_bracket", 30),
                )
            }]
        )

        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(text)

        log.info("investment_manager.complete", strategy=result.get("strategy_name", ""))
        return result
