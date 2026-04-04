"""
Company Intelligence Agent — The Stock Picker.
Investment Manager Agent — Full investment playbook builder.
UPDATED: Added FreeDataAggregator for premium-grade data at zero cost.
"""
import json
import structlog
from datetime import datetime

from utils.llm_client import call_llm

logger = structlog.get_logger()

# ─── Prompts ──────────────────────────────────────────────────────────────────

COMPANY_PICKER_PROMPT = """You are a senior equity research analyst specializing in Indian markets (NSE/BSE).

Your job is to identify the BEST specific companies to invest in, given the current market signals and identified sectors.

CURRENT SIGNALS: {signals}
SECTORS TO BUY: {sectors_to_buy}
SECTORS TO AVOID: {sectors_to_avoid}
INVESTMENT AMOUNT: ₹{amount}
TIME HORIZON: {horizon}
USER RISK PROFILE: {risk_profile}
PREMIUM INTELLIGENCE (financials, transcripts, consensus): {premium_data}

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
            "Every $1 rise in Brent = ~₹400 crore additional profit"
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
PREMIUM INTELLIGENCE: {premium_intelligence}

BUILD A COMPLETE INVESTMENT PLAYBOOK.

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
          {{"instrument": "ONGC", "amount": 20000, "reason": "High conviction, oil signal peaking"}}
        ],
        "trigger": "Deploy immediately — don't wait"
      }}
    ]
  }},
  "sip_vs_lumpsum": {{
    "recommendation": "phased_lumpsum",
    "reasoning": "SIP is best for long-term equity wealth building (5+ years).",
    "if_sip_preferred": {{
      "monthly_amount": 8500,
      "duration_months": 12,
      "instruments": [
        {{"name": "Nifty 50 Index Fund", "monthly": 4000}}
      ]
    }}
  }},
  "rebalancing_schedule": [
    {{
      "at": "8 weeks",
      "action": "First review — check if signals have changed",
      "what_to_check": ["Brent crude price vs $95 threshold", "INR vs 84.5 level"],
      "if_signals_unchanged": "Hold all positions"
    }}
  ],
  "exit_strategy": {{
    "planned_exit": {{
      "date": "12 months from today",
      "method": "Gradual — sell 25% per month over final 4 months",
      "tax_note": "Hold equity >12 months for LTCG benefit at 10% vs STCG at 15%"
    }},
    "emergency_exits": [
      {{
        "trigger": "Portfolio falls more than 15% from peak",
        "action": "Exit small caps immediately, reduce equity to 30%",
        "reason": "Capital preservation over returns"
      }}
    ],
    "profit_booking": [
      {{
        "trigger": "Any single stock up 30% in < 3 months",
        "action": "Book 50% profit — let the rest run"
      }}
    ]
  }},
  "monthly_monitoring": {{
    "weekly_checks": ["India VIX level", "Brent crude price", "FII/DII daily flows"],
    "monthly_checks": ["Portfolio vs Nifty performance", "Signal status update"]
  }},
  "behavioral_guardrails": [
    "Never add more than planned if a stock is falling — only add if the THESIS is unchanged"
  ],
  "expected_outcome": {{
    "base_case_return": "12-16%",
    "best_case_return": "22-28%",
    "worst_case_return": "-8% to -12%",
    "probability_of_positive_return": "71%"
  }},
  "manager_note": "One honest note from your investment manager."
}}
"""

# ─── Company Fallback Database ─────────────────────────────────────────────────

COMPANY_DB = {
    "Oil & Gas": {
        "established": [
            {"name": "ONGC",      "symbol": "ONGC",     "cap": "large", "pe": 6.2,  "div_yield": 4.2, "revenue_growth": 18},
            {"name": "Oil India", "symbol": "OIL",      "cap": "mid",   "pe": 8.1,  "div_yield": 5.8, "revenue_growth": 22},
            {"name": "Reliance",  "symbol": "RELIANCE", "cap": "large", "pe": 24.0, "div_yield": 0.4, "revenue_growth": 12},
        ],
        "emerging": [{"name": "Selan Exploration", "symbol": "SELAN", "cap": "small", "pe": 15.0, "revenue_growth": 45}],
        "etf": {"name": "CPSE ETF", "symbol": "CPSEETF", "expense_ratio": 0.01},
    },
    "IT": {
        "established": [
            {"name": "TCS",      "symbol": "TCS",     "cap": "large", "pe": 28.0, "div_yield": 1.5, "revenue_growth": 14},
            {"name": "Infosys",  "symbol": "INFY",    "cap": "large", "pe": 24.0, "div_yield": 2.8, "revenue_growth": 11},
            {"name": "HCL Tech", "symbol": "HCLTECH", "cap": "large", "pe": 20.0, "div_yield": 4.1, "revenue_growth": 17},
        ],
        "emerging": [{"name": "Newgen Software", "symbol": "NEWGEN", "cap": "mid", "pe": 38.0, "revenue_growth": 32}],
        "etf": {"name": "Nifty IT ETF", "symbol": "ITBEES", "expense_ratio": 0.15},
    },
    "Banking": {
        "established": [
            {"name": "HDFC Bank",  "symbol": "HDFCBANK",  "cap": "large", "pe": 17.0, "div_yield": 1.2, "revenue_growth": 19},
            {"name": "ICICI Bank", "symbol": "ICICIBANK", "cap": "large", "pe": 16.5, "div_yield": 0.9, "revenue_growth": 23},
            {"name": "Kotak Bank", "symbol": "KOTAKBANK", "cap": "large", "pe": 18.0, "div_yield": 0.1, "revenue_growth": 18},
        ],
        "emerging": [{"name": "Ujjivan SFB", "symbol": "UJJIVANSFB", "cap": "small", "pe": 9.0, "revenue_growth": 41}],
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
            {"name": "L&T",        "symbol": "LT",        "cap": "large", "pe": 31.0, "div_yield": 0.8, "revenue_growth": 16},
            {"name": "Power Grid", "symbol": "POWERGRID", "cap": "large", "pe": 16.0, "div_yield": 4.5, "revenue_growth": 8},
            {"name": "IRFC",       "symbol": "IRFC",      "cap": "large", "pe": 29.0, "div_yield": 1.2, "revenue_growth": 25},
        ],
        "emerging": [{"name": "KPI Green Energy", "symbol": "KPIGREEN", "cap": "small", "pe": 35.0, "revenue_growth": 110}],
        "etf": {"name": "Nifty Infra ETF", "symbol": "INFRABEES", "expense_ratio": 0.20},
    },
    "Pharma": {
        "established": [
            {"name": "Sun Pharma",   "symbol": "SUNPHARMA", "cap": "large", "pe": 34.0, "div_yield": 0.8, "revenue_growth": 14},
            {"name": "Dr. Reddy's", "symbol": "DRREDDY",   "cap": "large", "pe": 22.0, "div_yield": 0.7, "revenue_growth": 18},
            {"name": "Cipla",        "symbol": "CIPLA",     "cap": "large", "pe": 25.0, "div_yield": 0.6, "revenue_growth": 13},
        ],
        "emerging": [{"name": "Gland Pharma", "symbol": "GLAND", "cap": "mid", "pe": 30.0, "revenue_growth": 28}],
        "etf": {"name": "Pharma ETF", "symbol": "PHARMABEES", "expense_ratio": 0.18},
    },
    "Defence": {
        "established": [
            {"name": "HAL",  "symbol": "HAL",  "cap": "large", "pe": 38.0, "div_yield": 0.5, "revenue_growth": 22},
            {"name": "BEL",  "symbol": "BEL",  "cap": "large", "pe": 40.0, "div_yield": 0.8, "revenue_growth": 18},
            {"name": "BHEL", "symbol": "BHEL", "cap": "large", "pe": 90.0, "div_yield": 0.3, "revenue_growth": 32},
        ],
        "emerging": [{"name": "Data Patterns", "symbol": "DATAPATTNS", "cap": "small", "pe": 65.0, "revenue_growth": 48}],
        "etf": {"name": "Mirae India Defence ETF", "symbol": "MIDEFTF", "expense_ratio": 0.35},
    },
    "Renewable Energy": {
        "established": [
            {"name": "Adani Green", "symbol": "ADANIGREEN", "cap": "large", "pe": 120.0, "div_yield": 0.0, "revenue_growth": 42},
            {"name": "Tata Power",  "symbol": "TATAPOWER",  "cap": "large", "pe": 40.0,  "div_yield": 0.4, "revenue_growth": 25},
            {"name": "NTPC Green",  "symbol": "NTPCGREEN",  "cap": "large", "pe": 85.0,  "div_yield": 0.2, "revenue_growth": 38},
        ],
        "emerging": [{"name": "Waaree Energies", "symbol": "WAAREE", "cap": "mid", "pe": 45.0, "revenue_growth": 78}],
        "etf": {"name": "Mirae Nifty India Manufacturing ETF", "symbol": "MFGE", "expense_ratio": 0.30},
    },
}


class CompanyIntelligenceAgent:
    def __init__(self, db_session=None):
        self.db = db_session

    async def analyze(self, inputs: dict) -> dict:
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

        enriched_sectors = self._enrich_sectors(sectors_to_buy)

        # ── Step 1: AI company picking ─────────────────────────────────────────
        result = await self._run_company_analysis(
            signals=signals,
            sectors_to_buy=enriched_sectors,
            sectors_to_avoid=sectors_to_avoid,
            amount=amount,
            horizon=horizon,
            risk_profile=risk_profile,
        )

        # ── Step 2: Enrich top picks with free premium data ────────────────────
        # Runs financials, consensus, broker research, transcripts, sector KPIs
        try:
            from agents.free_data_feeds import FreeDataAggregator
            aggregator  = FreeDataAggregator()
            top_stocks  = []
            for sector_pick in result.get("sector_picks", []):
                for company in sector_pick.get("companies", [])[:2]:
                    top_stocks.append({
                        "nse_symbol": company.get("nse_symbol", ""),
                        "name":       company.get("name", ""),
                        "sector":     sector_pick.get("sector", ""),
                    })

            if top_stocks:
                log.info("company_intelligence.enriching",
                         stocks=len(top_stocks[:4]))
                enriched = await aggregator.batch_analyze(top_stocks[:4])
                result["premium_intelligence"] = enriched
                log.info("company_intelligence.enriched",
                         enriched=len(enriched))
        except Exception as e:
            log.warning("company_intelligence.enrichment_failed", error=str(e))
            result["premium_intelligence"] = []

        log.info("company_intelligence.complete",
                 picks=len(result.get("sector_picks", [])))
        return result

    def _enrich_sectors(self, sectors_to_buy: list) -> list:
        enriched = []
        for sector_item in sectors_to_buy:
            sector_name = sector_item.get("sector", "") if isinstance(sector_item, dict) else sector_item
            db_data     = COMPANY_DB.get(sector_name, {})
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
        signals,
        sectors_to_buy,
        sectors_to_avoid,
        amount,
        horizon,
        risk_profile,
        premium_data: dict = None,
    ) -> dict:
        signals_summary = [
            {"title": s.get("title"), "type": s.get("signal_type"),
             "importance": s.get("importance_score")}
            for s in signals[:5]
        ]

        prompt = COMPANY_PICKER_PROMPT.format(
            signals=json.dumps(signals_summary, indent=2),
            sectors_to_buy=json.dumps(sectors_to_buy, indent=2),
            sectors_to_avoid=json.dumps(sectors_to_avoid, indent=2),
            amount=f"{amount:,.0f}",
            horizon=horizon,
            risk_profile=risk_profile,
            premium_data=json.dumps(premium_data or {}, indent=2)[:1000],
        )

        text = await call_llm(prompt, agent_name="company_intelligence")
        return json.loads(text)


class InvestmentManagerAgent:
    def __init__(self, db_session=None):
        self.db = db_session

    async def build_strategy(self, inputs: dict) -> dict:
        company_picks      = inputs.get("company_intelligence", {})
        signals            = inputs.get("signal_watcher", {}).get("signals", [])
        temporal           = inputs.get("temporal_agent", {})
        user_profile       = inputs.get("user_profile", {})
        amount             = inputs.get("amount", 100000)
        horizon            = inputs.get("horizon", "1 year")

        # Pull premium intelligence if available
        premium_intel = company_picks.get("premium_intelligence", [])

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

        # Summarize premium intelligence for prompt
        premium_summary = []
        for intel in premium_intel[:3]:
            symbol  = intel.get("symbol", "")
            consens = intel.get("consensus", {}).get("consensus_rating", "")
            tone    = intel.get("transcript", {}).get("management_tone", "")
            kpi_sig = intel.get("sector_kpis", {}).get("overall_signal", "")
            if symbol:
                premium_summary.append(
                    f"{symbol}: analyst={consens}, mgmt_tone={tone}, kpis={kpi_sig}"
                )

        prompt = INVESTMENT_MANAGER_PROMPT.format(
            amount=f"{amount:,.0f}",
            horizon=horizon,
            risk_profile=user_profile.get("risk_tolerance", "moderate"),
            monthly_income=user_profile.get("monthly_income_bracket", "unknown"),
            existing_holdings=json.dumps(
                user_profile.get("current_holdings", []), indent=2
            ),
            company_picks=json.dumps(
                company_picks.get("sector_picks", [])[:3], indent=2
            )[:2000],
            signals_summary=signals_summary,
            temporal_outlook=temporal_outlook,
            tax_bracket=user_profile.get("tax_bracket", 30),
            premium_intelligence="\n".join(premium_summary) if premium_summary
                                  else "Premium data not available for this query",
        )

        text   = await call_llm(prompt, agent_name="investment_manager")
        result = json.loads(text)

        log.info("investment_manager.complete",
                 strategy=result.get("strategy_name", ""))
        return result