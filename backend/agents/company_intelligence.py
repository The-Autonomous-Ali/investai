"""
Company Intelligence Agent — Sector & company analysis using live data.
Investment Manager Agent — Market environment analysis and educational context.
UPDATED: Real data from yfinance + FreeDataAggregator replaces hardcoded COMPANY_DB.
SEBI Option 1: Show analysis, user decides. No buy/sell recommendations.
"""
import json
import structlog
from datetime import datetime

from utils.llm_client import call_llm

logger = structlog.get_logger()

# ─── Prompts ──────────────────────────────────────────────────────────────────

COMPANY_PICKER_PROMPT = """You are a direct equity analyst for Indian markets. State clear setups — which companies show strong signals and which to avoid right now.

Use ONLY numbers from the live data provided. Do not invent any figures.

CURRENT SIGNALS: {signals}
SECTORS SHOWING STRENGTH: {sectors_to_buy}
SECTORS SHOWING RISK: {sectors_to_avoid}
TIME HORIZON: {horizon}
USER RISK PROFILE: {risk_profile}

LIVE MARKET DATA: {live_market_data}
PREMIUM INTELLIGENCE: {premium_data}

For each strong sector, identify the 2-3 best-positioned companies and 1 ETF alternative.

Return ONLY valid JSON:
{{
  "sector_picks": [
    {{
      "sector": "IT",
      "signal_fit_score": 9.2,
      "signal_fit_reason": "Direct link to current signal — e.g. rupee weakness + US tech demand = IT revenue boost",
      "companies": [
        {{
          "name": "TCS",
          "nse_symbol": "TCS",
          "type": "established",
          "category": "large_cap",
          "setup": "BULLISH",
          "setup_strength": "strong|moderate|weak",
          "why_relevant": [
            "Primary reason tied to current signal — use data from LIVE MARKET DATA",
            "Supporting data point"
          ],
          "data_highlights": {{
            "source": "live_market_data or premium_intelligence",
            "key_metrics": "ONLY numbers from the provided data — price, PE, revenue, etc."
          }},
          "risk_level": "low|medium|high",
          "key_risk": "Single biggest risk for this stock right now",
          "signal_alignment": "high|medium|low",
          "entry_trigger": "What data point would confirm this is a good entry",
          "exit_trigger": "What would signal to exit this position"
        }}
      ],
      "etf_alternative": {{
        "name": "Nifty IT ETF",
        "symbol": "ITBEES",
        "why_relevant": "Lower single-stock risk, tracks the whole IT sector"
      }}
    }}
  ],
  "analysis_note": "1-2 sentence direct summary of the strongest setup right now",
  "data_freshness": "{data_timestamp}",
  "total_companies_analysed": 8
}}
"""

INVESTMENT_MANAGER_PROMPT = """You are a market analyst providing educational context about investment approaches for Indian retail investors.

IMPORTANT RULES:
- Do NOT recommend specific amounts to invest in specific instruments.
- Do NOT provide deployment plans with specific timing and amounts.
- Do NOT predict specific return percentages or probabilities.
- Frame everything as education and analysis, not advice.
- Reference data and historical patterns, not predictions.

USER CONTEXT:
- Available Amount: {amount}
- Time Horizon: {horizon}
- Risk Profile: {risk_profile}
- Current Holdings: {existing_holdings}

COMPANIES ANALYSED: {company_picks}
MARKET SIGNALS: {signals_summary}
TEMPORAL OUTLOOK: {temporal_outlook}
PREMIUM INTELLIGENCE: {premium_intelligence}

Provide educational market context and analysis.

Return ONLY valid JSON:
{{
  "strategy_context": "2-3 paragraph analytical explanation of how current signals relate to the identified sectors and companies. Reference specific data points.",
  "market_environment_analysis": {{
    "current_phase": "Description of current market environment",
    "key_factors": [
      {{"factor": "Factor name", "data_point": "Real data citation", "implication": "What this typically means historically"}}
    ],
    "historical_context": "How similar signal combinations have played out historically (general patterns, not predictions)"
  }},
  "approach_considerations": {{
    "sip_vs_lumpsum_education": "General education about when each approach has historically worked better — not a recommendation",
    "time_horizon_factors": "What the user's time horizon means for different approaches",
    "risk_matching": "How the user's risk profile relates to the current market environment"
  }},
  "monitoring_framework": {{
    "key_indicators_to_watch": ["Indicator 1", "Indicator 2"],
    "signal_change_triggers": ["What would change the analysis"],
    "suggested_review_cadence": "How often to reassess"
  }},
  "risk_awareness": {{
    "key_risks": ["Risk 1 with explanation", "Risk 2 with explanation"],
    "thesis_invalidation": "What conditions would make this analysis outdated",
    "behavioral_notes": ["Common mistakes investors make in this type of market"]
  }},
  "tax_education": {{
    "ltcg_stcg_note": "Factual explanation of India's LTCG/STCG rules",
    "holding_period_impact": "How holding period affects tax treatment"
  }},
  "disclaimer": "This analysis is for educational and informational purposes only. It does not constitute investment advice under SEBI (Investment Advisers) Regulations, 2013. Please consult a SEBI-registered investment advisor before making investment decisions."
}}
"""

# ─── Sector → Company mapping (names and symbols only, NO financial metrics) ──

SECTOR_COMPANIES = {
    "Oil & Gas": {
        "established": [
            {"name": "ONGC", "symbol": "ONGC"},
            {"name": "Oil India", "symbol": "OIL"},
            {"name": "Reliance", "symbol": "RELIANCE"},
        ],
        "emerging": [{"name": "Selan Exploration", "symbol": "SELAN"}],
        "etf": {"name": "CPSE ETF", "symbol": "CPSEETF"},
    },
    "IT": {
        "established": [
            {"name": "TCS", "symbol": "TCS"},
            {"name": "Infosys", "symbol": "INFY"},
            {"name": "HCL Tech", "symbol": "HCLTECH"},
        ],
        "emerging": [{"name": "Newgen Software", "symbol": "NEWGEN"}],
        "etf": {"name": "Nifty IT ETF", "symbol": "ITBEES"},
    },
    "Banking": {
        "established": [
            {"name": "HDFC Bank", "symbol": "HDFCBANK"},
            {"name": "ICICI Bank", "symbol": "ICICIBANK"},
            {"name": "Kotak Bank", "symbol": "KOTAKBANK"},
        ],
        "emerging": [{"name": "Ujjivan SFB", "symbol": "UJJIVANSFB"}],
        "etf": {"name": "Bank Nifty ETF", "symbol": "BANKBEES"},
    },
    "Gold": {
        "established": [
            {"name": "Sovereign Gold Bond 2029", "symbol": "SGBMAR29"},
            {"name": "Nippon Gold ETF", "symbol": "GOLDBEES"},
        ],
        "emerging": [],
        "etf": {"name": "Nippon Gold ETF", "symbol": "GOLDBEES"},
    },
    "Infrastructure": {
        "established": [
            {"name": "L&T", "symbol": "LT"},
            {"name": "Power Grid", "symbol": "POWERGRID"},
            {"name": "IRFC", "symbol": "IRFC"},
        ],
        "emerging": [{"name": "KPI Green Energy", "symbol": "KPIGREEN"}],
        "etf": {"name": "Nifty Infra ETF", "symbol": "INFRABEES"},
    },
    "Pharma": {
        "established": [
            {"name": "Sun Pharma", "symbol": "SUNPHARMA"},
            {"name": "Dr. Reddy's", "symbol": "DRREDDY"},
            {"name": "Cipla", "symbol": "CIPLA"},
        ],
        "emerging": [{"name": "Gland Pharma", "symbol": "GLAND"}],
        "etf": {"name": "Pharma ETF", "symbol": "PHARMABEES"},
    },
    "Defence": {
        "established": [
            {"name": "HAL", "symbol": "HAL"},
            {"name": "BEL", "symbol": "BEL"},
            {"name": "BHEL", "symbol": "BHEL"},
        ],
        "emerging": [{"name": "Data Patterns", "symbol": "DATAPATTNS"}],
        "etf": {"name": "Mirae India Defence ETF", "symbol": "MIDEFTF"},
    },
    "Renewable Energy": {
        "established": [
            {"name": "Adani Green", "symbol": "ADANIGREEN"},
            {"name": "Tata Power", "symbol": "TATAPOWER"},
            {"name": "NTPC Green", "symbol": "NTPCGREEN"},
        ],
        "emerging": [{"name": "Waaree Energies", "symbol": "WAAREE"}],
        "etf": {"name": "Mirae Nifty India Manufacturing ETF", "symbol": "MFGE"},
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

        # ── Step 1: Fetch live market data for sector companies ───────────────
        enriched_sectors, live_market_data = await self._enrich_sectors(sectors_to_buy)

        # ── Step 2: Fetch premium intelligence BEFORE the LLM call ────────────
        premium_data = {}
        try:
            from agents.free_data_feeds import FreeDataAggregator
            aggregator = FreeDataAggregator()
            top_stocks = []
            for sector_info in enriched_sectors:
                for company in sector_info.get("companies", [])[:2]:
                    top_stocks.append({
                        "nse_symbol": company.get("symbol", ""),
                        "name":       company.get("name", ""),
                        "sector":     sector_info.get("sector", ""),
                    })

            if top_stocks:
                log.info("company_intelligence.enriching",
                         stocks=len(top_stocks[:4]))
                enriched = await aggregator.batch_analyze(top_stocks[:4])
                premium_data = enriched
                log.info("company_intelligence.enriched",
                         enriched=len(enriched))
        except Exception as e:
            log.warning("company_intelligence.enrichment_failed", error=str(e))

        # ── Step 3: AI analysis with real data ────────────────────────────────
        result = await self._run_company_analysis(
            signals=signals,
            sectors_to_buy=enriched_sectors,
            sectors_to_avoid=sectors_to_avoid,
            amount=amount,
            horizon=horizon,
            risk_profile=risk_profile,
            live_market_data=live_market_data,
            premium_data=premium_data,
        )

        result["premium_intelligence"] = premium_data if premium_data else []

        log.info("company_intelligence.complete",
                 picks=len(result.get("sector_picks", [])))
        return result

    async def _enrich_sectors(self, sectors_to_buy: list) -> tuple:
        """Fetch live yfinance data for companies in target sectors.

        Returns (enriched_sectors, live_market_data_dict).
        """
        from scrapers.market_data import get_stock_data

        enriched = []
        live_market_data = {}

        for sector_item in sectors_to_buy:
            sector_name = sector_item.get("sector", "") if isinstance(sector_item, dict) else sector_item
            sector_data = SECTOR_COMPANIES.get(sector_name, {})

            all_companies = (
                sector_data.get("established", []) +
                sector_data.get("emerging", [])
            )

            companies_with_data = []
            for company in all_companies:
                symbol = company["symbol"]
                try:
                    stock_data = await get_stock_data(symbol)
                    live_market_data[symbol] = stock_data
                    companies_with_data.append({
                        "name": company["name"],
                        "symbol": symbol,
                        "live_data": stock_data,
                    })
                except Exception as e:
                    logger.warning("company_intelligence.stock_data_failed",
                                   symbol=symbol, error=str(e))
                    companies_with_data.append({
                        "name": company["name"],
                        "symbol": symbol,
                        "live_data": None,
                    })

            enriched.append({
                "sector":     sector_name,
                "reason":     sector_item.get("reason", "") if isinstance(sector_item, dict) else "",
                "instruments": sector_item.get("instruments", []) if isinstance(sector_item, dict) else [],
                "companies":  companies_with_data,
                "etf":        sector_data.get("etf", {}),
            })

        return enriched, live_market_data

    async def _run_company_analysis(
        self,
        signals,
        sectors_to_buy,
        sectors_to_avoid,
        amount,
        horizon,
        risk_profile,
        live_market_data: dict = None,
        premium_data: dict = None,
    ) -> dict:
        signals_summary = [
            {"title": s.get("title"), "type": s.get("signal_type"),
             "importance": s.get("importance_score")}
            for s in signals[:5]
        ]

        prompt = COMPANY_PICKER_PROMPT.format(
            signals=json.dumps(signals_summary, indent=2),
            sectors_to_buy=json.dumps(sectors_to_buy, indent=2)[:3000],
            sectors_to_avoid=json.dumps(sectors_to_avoid, indent=2),
            amount=f"{amount:,.0f}",
            horizon=horizon,
            risk_profile=risk_profile,
            live_market_data=json.dumps(live_market_data or {}, indent=2)[:2000],
            premium_data=json.dumps(premium_data or {}, indent=2)[:1500],
            data_timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

        try:
            text = await call_llm(prompt, agent_name="company_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("company_intelligence.llm_failed", error=str(e)[:200])
            return {"sector_picks": [], "error": f"analysis_failed: {str(e)[:100]}"}


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

        premium_summary = []
        for intel in (premium_intel[:3] if isinstance(premium_intel, list) else []):
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
            existing_holdings=json.dumps(
                user_profile.get("current_holdings", []), indent=2
            ),
            company_picks=json.dumps(
                company_picks.get("sector_picks", [])[:3], indent=2
            )[:2000],
            signals_summary=signals_summary,
            temporal_outlook=temporal_outlook,
            premium_intelligence="\n".join(premium_summary) if premium_summary
                                  else "Premium data not available for this query",
        )

        text   = await call_llm(prompt, agent_name="investment_manager")
        result = json.loads(text)

        log.info("investment_manager.complete",
                 strategy=result.get("strategy_context", "")[:80])
        return result
