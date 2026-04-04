"""
Market Intelligence Module — 8 Advanced Analysis Features

1. BulkDealMonitor        — NSE bulk/block deals (smart money tracker)
2. InsiderTradingMonitor  — Promoter/director buy/sell disclosures
3. EarningsCalendar       — Upcoming results schedule
4. SectorRotationModel    — Which sectors win in which macro environment
5. FIISectoralFlowTracker — Where FII money is flowing by sector
6. MutualFundTracker      — Top fund holdings from AMFI
7. MaxPainCalculator      — Options expiry price prediction
8. OptionsChainAnalyzer   — Put/Call ratio + institutional positioning

All sources: NSE India, BSE India, AMFI — completely free, no API key needed.
"""

import json
import asyncio
import structlog
import httpx
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from utils.llm_client import call_llm

logger  = structlog.get_logger()
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}


# ═════════════════════════════════════════════════════════════════════════════
# HELPER — NSE Session (handles cookies automatically)
# ═════════════════════════════════════════════════════════════════════════════

async def get_nse_client() -> httpx.AsyncClient:
    """Create an httpx client with NSE cookies pre-loaded."""
    client = httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True)
    try:
        await client.get("https://www.nseindia.com/")
        await client.get("https://www.nseindia.com/market-data/live-equity-market")
    except Exception:
        pass
    return client


# ═════════════════════════════════════════════════════════════════════════════
# 1. BULK DEAL & BLOCK DEAL MONITOR
# Source: NSE (free) — nseindia.com/api/bulk-deals
# ═════════════════════════════════════════════════════════════════════════════

BULK_DEAL_ANALYSIS_PROMPT = """You are analyzing bulk and block deal data from NSE India.

These are large institutional trades — when a big investor buys/sells 0.5%+ of a company
in a single session, NSE must disclose it publicly.

BULK DEALS TODAY: {bulk_deals}
BLOCK DEALS TODAY: {block_deals}

Identify the most significant smart money moves. Return ONLY valid JSON:
{{
  "most_significant_deals": [
    {{
      "symbol":         "ONGC",
      "deal_type":      "bulk|block",
      "side":           "buy|sell",
      "quantity":       500000,
      "value_crore":    132.5,
      "buyer_seller":   "Name of institution if disclosed",
      "signal":         "bullish|bearish",
      "significance":   "high|medium|low",
      "interpretation": "What this deal means — plain language",
      "action_for_retail": "What a retail investor should note"
    }}
  ],
  "net_smart_money_direction": "bullish|bearish|mixed",
  "sectors_seeing_accumulation": ["Sector names"],
  "sectors_seeing_distribution": ["Sector names"],
  "key_insight": "One sentence — the most important thing retail investors should know from today's deals"
}}
"""


class BulkDealMonitor:
    """
    Monitors NSE bulk and block deals.
    These are the footprints of institutional money — invaluable for retail investors.

    Bulk deal:  Single client buys/sells >0.5% of company shares in one session
    Block deal: Large trade (>500 shares or >₹5 crore) done in opening 35 minutes
    """

    NSE_BULK_URL  = "https://www.nseindia.com/api/bulk-deals?date={date}"
    NSE_BLOCK_URL = "https://www.nseindia.com/api/block-deals"

    async def get_today_deals(self) -> dict:
        """Fetch today's bulk and block deals from NSE."""
        log = logger.bind(source="bulk_deal_monitor")
        log.info("bulk_deal_monitor.fetch")

        today = datetime.now().strftime("%d-%m-%Y")
        client = await get_nse_client()

        bulk_deals  = []
        block_deals = []

        try:
            # Fetch bulk deals
            r = await client.get(self.NSE_BULK_URL.format(date=today))
            if r.status_code == 200:
                data       = r.json()
                bulk_deals = data.get("data", [])

            # Fetch block deals
            r = await client.get(self.NSE_BLOCK_URL)
            if r.status_code == 200:
                data        = r.json()
                block_deals = data.get("data", [])

        except Exception as e:
            log.warning("bulk_deal_monitor.fetch_error", error=str(e))
        finally:
            await client.aclose()

        if not bulk_deals and not block_deals:
            return self._get_fallback()

        # AI analysis
        result = await self._analyze(bulk_deals[:20], block_deals[:20])
        result["raw_bulk_deals"]  = bulk_deals[:10]
        result["raw_block_deals"] = block_deals[:10]
        result["fetched_at"]      = datetime.utcnow().isoformat()
        result["data_source"]     = "NSE India"

        log.info("bulk_deal_monitor.complete",
                 bulk=len(bulk_deals), block=len(block_deals))
        return result

    async def get_deals_for_symbol(self, symbol: str, days: int = 30) -> list:
        """Get recent bulk/block deals for a specific stock."""
        client = await get_nse_client()
        deals  = []

        try:
            for i in range(min(days, 10)):
                date = (datetime.now() - timedelta(days=i)).strftime("%d-%m-%Y")
                r    = await client.get(self.NSE_BULK_URL.format(date=date))
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    symbol_deals = [d for d in data if d.get("symbol") == symbol]
                    deals.extend(symbol_deals)
        except Exception as e:
            logger.warning("bulk_deal_monitor.symbol_error", symbol=symbol, error=str(e))
        finally:
            await client.aclose()

        return deals

    async def _analyze(self, bulk_deals: list, block_deals: list) -> dict:
        prompt = BULK_DEAL_ANALYSIS_PROMPT.format(
            bulk_deals=json.dumps(bulk_deals[:15], indent=2)[:2000],
            block_deals=json.dumps(block_deals[:10], indent=2)[:1000],
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("bulk_deal_monitor.analysis_error", error=str(e))
            return {"key_insight": "Deal data fetched but analysis unavailable"}

    def _get_fallback(self) -> dict:
        return {
            "most_significant_deals":      [],
            "net_smart_money_direction":   "unknown",
            "sectors_seeing_accumulation": [],
            "sectors_seeing_distribution": [],
            "key_insight":                 "No bulk/block deals found for today — market may be closed or data delayed",
            "fetched_at":                  datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# 2. INSIDER TRADING MONITOR
# Source: NSE SAST/SEBI disclosures (free)
# ═════════════════════════════════════════════════════════════════════════════

INSIDER_ANALYSIS_PROMPT = """You are analyzing insider trading disclosures from NSE India.

When promoters, directors, or key management buy their own company's stock,
it is the strongest possible bullish signal. When they sell — it's a warning.

INSIDER TRANSACTIONS: {transactions}

Analyze and return ONLY valid JSON:
{{
  "significant_insider_buys": [
    {{
      "symbol":        "ONGC",
      "insider_name":  "Name",
      "insider_role":  "Promoter|Director|CEO|CFO",
      "transaction":   "buy|sell",
      "shares":        50000,
      "value_lakh":    132.5,
      "date":          "YYYY-MM-DD",
      "signal":        "very_bullish|bullish|neutral|bearish|very_bearish",
      "interpretation": "Plain language — what this means",
      "conviction":    "high|medium|low"
    }}
  ],
  "significant_insider_sells": [],
  "overall_insider_sentiment": "bullish|bearish|mixed|neutral",
  "stocks_with_promoter_buying": ["List of symbols"],
  "stocks_with_promoter_selling": ["List of symbols"],
  "red_flag_alert": "Any concerning patterns — e.g. promoter selling before bad results",
  "key_insight": "Most important insider signal for retail investors right now"
}}
"""


class InsiderTradingMonitor:
    """
    Monitors SEBI-mandated insider trading disclosures.
    Promoter buying own stock = CEO has skin in the game = strongest buy signal.
    Promoter selling = potential warning — needs context.
    """

    NSE_INSIDER_URL = "https://www.nseindia.com/api/corporates-pit?index=equities&from_date={from_date}&to_date={to_date}"

    async def get_recent_insider_trades(self, days: int = 7) -> dict:
        """Fetch insider trading disclosures for the past N days."""
        log = logger.bind(source="insider_monitor")
        log.info("insider_monitor.fetch", days=days)

        to_date   = datetime.now().strftime("%d-%m-%Y")
        from_date = (datetime.now() - timedelta(days=days)).strftime("%d-%m-%Y")

        client       = await get_nse_client()
        transactions = []

        try:
            r = await client.get(
                self.NSE_INSIDER_URL.format(from_date=from_date, to_date=to_date)
            )
            if r.status_code == 200:
                data         = r.json()
                transactions = data.get("data", [])
        except Exception as e:
            log.warning("insider_monitor.fetch_error", error=str(e))
        finally:
            await client.aclose()

        if not transactions:
            return self._get_fallback()

        result = await self._analyze(transactions[:30])
        result["total_disclosures"] = len(transactions)
        result["period_days"]       = days
        result["fetched_at"]        = datetime.utcnow().isoformat()
        result["data_source"]       = "NSE India SAST"

        log.info("insider_monitor.complete", transactions=len(transactions))
        return result

    async def get_symbol_insider_activity(self, symbol: str) -> dict:
        """Check if insiders of a specific company are buying or selling."""
        all_data = await self.get_recent_insider_trades(days=90)
        buys  = [d for d in all_data.get("significant_insider_buys",  []) if d.get("symbol") == symbol]
        sells = [d for d in all_data.get("significant_insider_sells", []) if d.get("symbol") == symbol]
        return {
            "symbol":          symbol,
            "recent_buys":     buys,
            "recent_sells":    sells,
            "net_signal":      "bullish" if len(buys) > len(sells) else
                               "bearish" if len(sells) > len(buys) else "neutral",
        }

    async def _analyze(self, transactions: list) -> dict:
        prompt = INSIDER_ANALYSIS_PROMPT.format(
            transactions=json.dumps(transactions[:20], indent=2)[:2500],
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("insider_monitor.analysis_error", error=str(e))
            return {"key_insight": "Insider data fetched but analysis unavailable"}

    def _get_fallback(self) -> dict:
        return {
            "significant_insider_buys":   [],
            "significant_insider_sells":  [],
            "overall_insider_sentiment":  "neutral",
            "stocks_with_promoter_buying": [],
            "key_insight":                "No insider disclosures found for this period",
            "fetched_at":                 datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# 3. EARNINGS CALENDAR
# Source: NSE India (free)
# ═════════════════════════════════════════════════════════════════════════════

EARNINGS_CALENDAR_PROMPT = """You are analyzing upcoming earnings results schedule for Indian companies.

UPCOMING RESULTS: {upcoming_results}
USER'S PORTFOLIO/WATCHLIST: {watchlist}

Provide actionable guidance. Return ONLY valid JSON:
{{
  "upcoming_results": [
    {{
      "symbol":           "HDFC Bank",
      "result_date":      "YYYY-MM-DD",
      "days_from_now":    3,
      "quarter":          "Q3 FY25",
      "market_expectation": "Revenue growth of ~18%, PAT ~₹16,000 crore",
      "pre_result_risk":  "high|medium|low",
      "recommended_action": "Do NOT buy fresh within 3 days of results — wait",
      "if_beat_expectation": "Stock likely to jump 3-5%",
      "if_miss_expectation": "Stock likely to fall 5-8%"
    }}
  ],
  "results_this_week":  ["HDFC Bank", "TCS"],
  "results_next_week":  ["Infosys", "ICICI Bank"],
  "high_risk_period":   "3 days before and after results — avoid fresh entry",
  "opportunity_stocks": ["Stocks where results could be surprise — worth watching"],
  "key_advice":         "Plain language calendar advice for next 2 weeks"
}}
"""


class EarningsCalendar:
    """
    Tracks upcoming quarterly results schedule.
    Critical for entry timing — never buy blind into results.
    """

    NSE_CALENDAR_URL = "https://www.nseindia.com/api/event-calendar"

    async def get_upcoming_results(self, days_ahead: int = 14) -> dict:
        """Get earnings calendar for next N days."""
        log = logger.bind(source="earnings_calendar")
        log.info("earnings_calendar.fetch", days_ahead=days_ahead)

        client  = await get_nse_client()
        results = []

        try:
            r = await client.get(self.NSE_CALENDAR_URL)
            if r.status_code == 200:
                data    = r.json()
                cutoff  = datetime.now() + timedelta(days=days_ahead)
                results = [
                    event for event in data
                    if event.get("purpose", "").lower() in
                    ("board meeting", "quarterly results", "financial results", "annual results")
                ]
        except Exception as e:
            log.warning("earnings_calendar.fetch_error", error=str(e))
        finally:
            await client.aclose()

        if not results:
            return self._get_fallback()

        analyzed = await self._analyze(results[:30], watchlist=[])
        analyzed["raw_events"] = results[:20]
        analyzed["fetched_at"] = datetime.utcnow().isoformat()
        analyzed["data_source"] = "NSE India"

        log.info("earnings_calendar.complete", events=len(results))
        return analyzed

    async def check_symbol_results(self, symbol: str) -> dict:
        """Check if a specific symbol has upcoming results."""
        calendar = await self.get_upcoming_results(days_ahead=30)
        upcoming = [
            e for e in calendar.get("upcoming_results", [])
            if e.get("symbol") == symbol
        ]
        if upcoming:
            next_result  = upcoming[0]
            days_to_result = next_result.get("days_from_now", 999)
            return {
                "symbol":        symbol,
                "has_upcoming":  True,
                "next_result":   next_result,
                "risk_level":    "high" if days_to_result <= 3 else
                                 "medium" if days_to_result <= 7 else "low",
                "advice":        f"Results in {days_to_result} days — {'AVOID fresh entry' if days_to_result <= 3 else 'Monitor closely'}",
            }
        return {
            "symbol":       symbol,
            "has_upcoming": False,
            "advice":       "No results scheduled in next 30 days — safe to enter",
        }

    async def _analyze(self, results: list, watchlist: list) -> dict:
        prompt = EARNINGS_CALENDAR_PROMPT.format(
            upcoming_results=json.dumps(results[:20], indent=2)[:2000],
            watchlist=json.dumps(watchlist),
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("earnings_calendar.analysis_error", error=str(e))
            return {"key_advice": "Earnings data fetched but analysis unavailable"}

    def _get_fallback(self) -> dict:
        return {
            "upcoming_results": [],
            "results_this_week": [],
            "results_next_week": [],
            "key_advice": "No earnings calendar data available — check NSE website directly",
            "fetched_at": datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# 4. SECTOR ROTATION MODEL
# No external API — pure macro analysis using existing signals
# ═════════════════════════════════════════════════════════════════════════════

SECTOR_ROTATION_PROMPT = """You are a sector rotation specialist for Indian markets (NSE/BSE).

Based on the current macro environment, identify which sectors are at peak, which are
entering growth, which are declining, and which are bottoming out.

CURRENT MACRO ENVIRONMENT:
{macro_data}

MARKET SIGNALS:
{signals}

INDIA VIX: {india_vix}
FII FLOWS: {fii_flows}
GLOBAL RISK REGIME: {risk_regime}

The classic sector rotation cycle for India:
1. Recovery: Banking, Real Estate, Auto (rate-sensitive sectors lead)
2. Expansion: IT, FMCG, Capital Goods (broad market growth)
3. Slowdown: Defensives — Pharma, FMCG, Gold (safety seeking)
4. Contraction: Gold, Bonds, Defensive FMCG (capital preservation)

Return ONLY valid JSON:
{{
  "current_cycle_phase": "recovery|expansion|slowdown|contraction",
  "cycle_confidence":    0.0-1.0,
  "cycle_explanation":   "Plain language — where we are in the cycle and why",
  "sector_rankings": [
    {{
      "sector":          "Oil & Gas",
      "rotation_phase":  "peak|entering_growth|declining|bottoming",
      "momentum":        "accelerating|stable|decelerating",
      "recommended":     "overweight|neutral|underweight",
      "reason":          "Why this sector is here in the cycle",
      "catalyst_to_watch": "What would change this view",
      "historical_example": "When was India last in this exact setup"
    }}
  ],
  "money_moving_into":   ["Sectors currently attracting institutional flows"],
  "money_moving_out_of": ["Sectors seeing institutional selling"],
  "next_rotation":       "Which sectors likely to lead in next 3-6 months",
  "portfolio_positioning": {{
    "overweight":  ["Sector 1", "Sector 2"],
    "neutral":     ["Sector 3"],
    "underweight": ["Sector 4", "Sector 5"]
  }},
  "key_rotation_signal": "One metric to watch that will signal the next rotation"
}}
"""


class SectorRotationModel:
    """
    Models sector rotation based on macro environment.
    Maps current conditions to historical sector performance patterns.
    No external API needed — uses existing signal and macro data.
    """

    async def analyze(
        self,
        macro_snapshot: dict,
        signals: list,
        india_vix: float = 17.0,
        fii_flows: float = None,
        risk_regime: str = "neutral",
    ) -> dict:
        """Identify current sector rotation phase and positioning."""
        log = logger.bind(source="sector_rotation")
        log.info("sector_rotation.analyze")

        prompt = SECTOR_ROTATION_PROMPT.format(
            macro_data=json.dumps({
                "nifty50":      macro_snapshot.get("nifty50", {}).get("value"),
                "brent_crude":  macro_snapshot.get("brent_crude", {}).get("value"),
                "us_10y_yield": macro_snapshot.get("us_10y_yield", {}).get("value"),
                "usd_inr":      macro_snapshot.get("usd_inr", {}).get("value"),
                "gold_spot":    macro_snapshot.get("gold_spot", {}).get("value"),
                "dxy":          macro_snapshot.get("dxy", {}).get("value"),
            }, indent=2),
            signals=json.dumps([
                {"title": s.get("title"), "type": s.get("signal_type"),
                 "geography": s.get("geography"), "sentiment": s.get("sentiment")}
                for s in signals[:8]
            ], indent=2),
            india_vix=india_vix,
            fii_flows=fii_flows or "Data unavailable",
            risk_regime=risk_regime,
        )

        try:
            text   = await call_llm(prompt, agent_name="market_intelligence")
            result = json.loads(text)
            result["analyzed_at"] = datetime.utcnow().isoformat()
            log.info("sector_rotation.complete",
                     phase=result.get("current_cycle_phase"))
            return result
        except Exception as e:
            log.warning("sector_rotation.error", error=str(e))
            return {
                "current_cycle_phase": "unknown",
                "cycle_explanation":   "Sector rotation analysis unavailable",
                "sector_rankings":     [],
                "analyzed_at":         datetime.utcnow().isoformat(),
            }


# ═════════════════════════════════════════════════════════════════════════════
# 5. FII SECTORAL FLOW TRACKER
# Source: NSE India (free)
# ═════════════════════════════════════════════════════════════════════════════

FII_SECTOR_PROMPT = """You are analyzing FII (Foreign Institutional Investor) sectoral flow data for India.

FII flows by sector tell you WHERE the big money is going — much more useful than just net total.

FII SECTORAL DATA: {fii_sector_data}
OVERALL FII FLOW TODAY: {total_fii}

Analyze and return ONLY valid JSON:
{{
  "total_fii_flow_crore": 0,
  "flow_direction": "net_buyer|net_seller",
  "sectors_attracting_fii": [
    {{
      "sector":         "Banking",
      "flow_crore":     850.5,
      "signal":         "bullish",
      "interpretation": "FII buying banking suggests confidence in rate cut expectations"
    }}
  ],
  "sectors_seeing_fii_exit": [],
  "concentration_alert": "Is FII buying concentrated in 1-2 sectors? High concentration = momentum trade",
  "dii_vs_fii": "Are domestic and foreign institutions agreeing or disagreeing?",
  "retail_implication": "What this sectoral flow means for a retail investor tomorrow",
  "tomorrow_watch": "Which sectors to watch at 9:15 AM NSE open based on today's flows"
}}
"""


class FIISectoralFlowTracker:
    """
    Tracks FII flows broken down by sector.
    Total FII net is in the market snapshot — this adds the crucial WHERE dimension.
    """

    NSE_FII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"

    async def get_sectoral_flows(self) -> dict:
        """Fetch today's FII/DII flows by sector."""
        log = logger.bind(source="fii_sectoral")
        log.info("fii_sectoral.fetch")

        client   = await get_nse_client()
        fii_data = []

        try:
            r = await client.get(self.NSE_FII_URL)
            if r.status_code == 200:
                fii_data = r.json()
        except Exception as e:
            log.warning("fii_sectoral.fetch_error", error=str(e))
        finally:
            await client.aclose()

        if not fii_data:
            return self._get_fallback()

        result = await self._analyze(fii_data)
        result["raw_data"]   = fii_data[:10]
        result["fetched_at"] = datetime.utcnow().isoformat()
        result["data_source"] = "NSE India"

        log.info("fii_sectoral.complete")
        return result

    async def _analyze(self, fii_data: list) -> dict:
        total_fii = sum(
            float(d.get("buyValue", 0)) - float(d.get("sellValue", 0))
            for d in fii_data if d.get("clientType") == "FII/FPI"
        )
        prompt = FII_SECTOR_PROMPT.format(
            fii_sector_data=json.dumps(fii_data[:15], indent=2)[:2000],
            total_fii=f"₹{total_fii:.0f} crore",
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("fii_sectoral.analysis_error", error=str(e))
            return {"retail_implication": "FII sectoral data fetched but analysis unavailable"}

    def _get_fallback(self) -> dict:
        return {
            "total_fii_flow_crore":       0,
            "flow_direction":             "unknown",
            "sectors_attracting_fii":     [],
            "sectors_seeing_fii_exit":    [],
            "retail_implication":         "FII sectoral data unavailable today",
            "fetched_at":                 datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# 6. MUTUAL FUND HOLDINGS TRACKER
# Source: AMFI India (free, monthly updates)
# ═════════════════════════════════════════════════════════════════════════════

MF_HOLDINGS_PROMPT = """You are analyzing mutual fund holdings data from AMFI India.

When top mutual funds increase their stake in a company, it's powerful institutional validation.
When they reduce — it's a warning signal worth noting.

MF HOLDINGS DATA: {holdings_data}
SYMBOL BEING CHECKED: {symbol}

Return ONLY valid JSON:
{{
  "symbol":                 "{symbol}",
  "total_mf_holding_pct":  15.2,
  "number_of_schemes":     42,
  "trend":                 "increasing|decreasing|stable",
  "top_funds_holding": [
    {{
      "fund_name":    "SBI Bluechip Fund",
      "holding_pct":  2.1,
      "change_mom":  "+0.3%",
      "signal":       "accumulating|reducing|stable"
    }}
  ],
  "institutional_conviction": "high|medium|low",
  "conviction_reason":        "Why conviction is at this level",
  "mf_signal":                "bullish|bearish|neutral",
  "retail_interpretation":    "Plain language — what MF activity means for retail investor",
  "smart_money_verdict":      "Are mutual funds buying or selling this stock?"
}}
"""


class MutualFundTracker:
    """
    Tracks mutual fund holdings from AMFI India.
    Monthly data but very powerful — 15 top funds buying = institutional validation.
    """

    AMFI_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
    NSE_MF_URL = "https://www.nseindia.com/api/corporates-pit?symbol={symbol}&issuer=&from_date={from}&to_date={to}&ca_type=ShareholdingPattern"

    async def get_mf_holdings(self, symbol: str) -> dict:
        """Get mutual fund holding data for a specific stock."""
        log = logger.bind(symbol=symbol, source="mf_tracker")
        log.info("mf_tracker.fetch")

        client       = await get_nse_client()
        holdings_raw = []

        try:
            to_date   = datetime.now().strftime("%d-%m-%Y")
            from_date = (datetime.now() - timedelta(days=90)).strftime("%d-%m-%Y")
            url = f"https://www.nseindia.com/api/shareholding-patterns?symbol={symbol}"
            r   = await client.get(url)
            if r.status_code == 200:
                holdings_raw = r.json()
        except Exception as e:
            log.warning("mf_tracker.fetch_error", symbol=symbol, error=str(e))
        finally:
            await client.aclose()

        if not holdings_raw:
            return self._get_fallback(symbol)

        result = await self._analyze(symbol, holdings_raw)
        result["fetched_at"]  = datetime.utcnow().isoformat()
        result["data_source"] = "NSE / AMFI India"

        log.info("mf_tracker.complete", symbol=symbol)
        return result

    async def _analyze(self, symbol: str, holdings_data) -> dict:
        prompt = MF_HOLDINGS_PROMPT.format(
            symbol=symbol,
            holdings_data=json.dumps(holdings_data, indent=2)[:2000]
            if isinstance(holdings_data, (dict, list))
            else str(holdings_data)[:2000],
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("mf_tracker.analysis_error", error=str(e))
            return self._get_fallback(symbol)

    def _get_fallback(self, symbol: str) -> dict:
        return {
            "symbol":                  symbol,
            "mf_signal":               "neutral",
            "smart_money_verdict":     "MF holdings data unavailable",
            "retail_interpretation":   "Check AMFI website for latest mutual fund holdings",
            "fetched_at":              datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# 7. MAX PAIN CALCULATOR
# Source: NSE Options Chain (free)
# ═════════════════════════════════════════════════════════════════════════════

MAX_PAIN_PROMPT = """You are explaining options max pain theory for Indian retail investors.

Max Pain is the strike price where option buyers lose the MOST money at expiry.
Option writers (big money) tend to push the price toward this level — so it's
a powerful predictor of where Nifty/stocks will close on expiry Thursday.

MAX PAIN CALCULATION:
Symbol:       {symbol}
Current Price: ₹{current_price}
Max Pain:      ₹{max_pain}
Expiry Date:   {expiry}
Days to Expiry: {dte}

Return ONLY valid JSON:
{{
  "symbol":           "{symbol}",
  "current_price":    {current_price},
  "max_pain_price":   {max_pain},
  "price_vs_max_pain": "+₹X above max pain" or "-₹X below max pain",
  "max_pain_signal":  "bullish|bearish|neutral",
  "expected_move":    "Price likely to move toward ₹{max_pain} before expiry",
  "expiry_date":      "{expiry}",
  "days_to_expiry":   {dte},
  "confidence":       0.0-1.0,
  "plain_explanation": "Imagine option writers are like a big casino. They want everyone to lose. Max pain is the price where most option buyers lose money. The casino has resources to push price there. So ₹{max_pain} is where smart money wants this to close on Thursday.",
  "trading_implication": "What a retail investor should do with this information",
  "caution": "Max pain works best in the last 2-3 days before expiry"
}}
"""


class MaxPainCalculator:
    """
    Calculates options max pain from NSE options chain.
    Tells you where the price is likely to close on expiry Thursday.
    Most powerful in last 2-3 days before weekly/monthly expiry.
    """

    NSE_OPTIONS_URL = "https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"

    async def calculate(self, symbol: str = "NIFTY") -> dict:
        """Calculate max pain from options chain data."""
        log = logger.bind(symbol=symbol, source="max_pain")
        log.info("max_pain.calculate")

        client       = await get_nse_client()
        options_data = None

        try:
            url = self.NSE_OPTIONS_URL.format(symbol=symbol)
            r   = await client.get(url)
            if r.status_code == 200:
                options_data = r.json()
        except Exception as e:
            log.warning("max_pain.fetch_error", error=str(e))
        finally:
            await client.aclose()

        if not options_data:
            return self._get_fallback(symbol)

        # Calculate max pain from options chain
        max_pain_result = self._compute_max_pain(options_data)

        if not max_pain_result:
            return self._get_fallback(symbol)

        # AI explanation
        result = await self._explain(symbol, max_pain_result)
        result["raw_max_pain"] = max_pain_result
        result["fetched_at"]   = datetime.utcnow().isoformat()
        result["data_source"]  = "NSE Options Chain"

        log.info("max_pain.complete",
                 symbol=symbol, max_pain=max_pain_result.get("max_pain"))
        return result

    def _compute_max_pain(self, options_data: dict) -> Optional[dict]:
        """Pure math — compute max pain strike from OI data."""
        try:
            records       = options_data.get("records", {})
            data          = records.get("data", [])
            current_price = records.get("underlyingValue", 0)
            expiry        = records.get("expiryDates", [""])[0]

            if not data or not current_price:
                return None

            # For each strike, calculate total pain (loss to option buyers)
            strikes     = {}
            for item in data:
                strike = item.get("strikePrice", 0)
                ce_oi  = item.get("CE", {}).get("openInterest", 0) or 0
                pe_oi  = item.get("PE", {}).get("openInterest", 0) or 0
                if strike not in strikes:
                    strikes[strike] = {"ce_oi": 0, "pe_oi": 0}
                strikes[strike]["ce_oi"] += ce_oi
                strikes[strike]["pe_oi"] += pe_oi

            strike_list = sorted(strikes.keys())
            min_pain    = float("inf")
            max_pain    = strike_list[len(strike_list) // 2]  # default to middle

            for test_strike in strike_list:
                total_pain = 0
                for strike, oi in strikes.items():
                    # Call buyer pain: if test_strike < strike, calls expire worthless
                    if test_strike < strike:
                        total_pain += oi["ce_oi"] * (strike - test_strike)
                    # Put buyer pain: if test_strike > strike, puts expire worthless
                    if test_strike > strike:
                        total_pain += oi["pe_oi"] * (test_strike - strike)

                if total_pain < min_pain:
                    min_pain = total_pain
                    max_pain = test_strike

            # Days to expiry
            try:
                expiry_dt  = datetime.strptime(expiry, "%d-%b-%Y")
                dte        = (expiry_dt - datetime.now()).days
            except Exception:
                dte = 7

            return {
                "symbol":        symbol if "symbol" in dir() else "NIFTY",
                "max_pain":      max_pain,
                "current_price": current_price,
                "expiry":        expiry,
                "dte":           dte,
            }

        except Exception as e:
            logger.warning("max_pain.compute_error", error=str(e))
            return None

    async def _explain(self, symbol: str, mp_data: dict) -> dict:
        prompt = MAX_PAIN_PROMPT.format(
            symbol=symbol,
            current_price=mp_data.get("current_price", 0),
            max_pain=mp_data.get("max_pain", 0),
            expiry=mp_data.get("expiry", ""),
            dte=mp_data.get("dte", 7),
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("max_pain.explain_error", error=str(e))
            return {
                "symbol":         symbol,
                "max_pain_price": mp_data.get("max_pain"),
                "plain_explanation": f"Max pain is ₹{mp_data.get('max_pain')} — price tends to gravitate here before expiry",
            }

    def _get_fallback(self, symbol: str) -> dict:
        return {
            "symbol":          symbol,
            "max_pain_price":  None,
            "plain_explanation": "Options data unavailable — check NSE website",
            "fetched_at":      datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# 8. OPTIONS CHAIN ANALYZER
# Source: NSE Options Chain (free)
# ═════════════════════════════════════════════════════════════════════════════

OPTIONS_CHAIN_PROMPT = """You are analyzing the NSE options chain for institutional positioning signals.

Put/Call ratio and OI concentration tell you what big money is hedging against.
High Put OI = institutions protecting against downside = bearish signal
High Call OI = institutions capping upside = stock unlikely to cross this level

OPTIONS CHAIN SUMMARY:
Symbol:        {symbol}
Current Price: ₹{current_price}
PCR (Put/Call Ratio): {pcr}
Highest Call OI Strike: ₹{max_call_strike} (resistance wall)
Highest Put OI Strike:  ₹{max_put_strike}  (support floor)

OI DATA: {oi_summary}

Return ONLY valid JSON:
{{
  "symbol":              "{symbol}",
  "current_price":       {current_price},
  "pcr":                 {pcr},
  "pcr_interpretation":  "PCR > 1.2 = bearish, 0.7-1.2 = neutral, < 0.7 = bullish",
  "market_sentiment":    "bullish|neutral|bearish",
  "key_resistance":      {max_call_strike},
  "key_support":         {max_put_strike},
  "resistance_explanation": "Huge call writing at ₹X means institutions don't expect stock to cross this",
  "support_explanation":    "Huge put writing at ₹X means institutions are protecting this floor",
  "oi_buildup_signal":   "Increasing OI = smart money adding positions (conviction)",
  "trading_range":       "Stock likely to trade between ₹X and ₹Y before expiry",
  "plain_explanation":   "Simple explanation for retail investor — what the options market is saying",
  "entry_implication":   "Should retail investor buy/sell/wait based on options data?",
  "key_levels_to_watch": [
    "₹X — if broken, market goes to ₹Y quickly",
    "₹Z — strong wall, don't expect easy breakout"
  ]
}}
"""


class OptionsChainAnalyzer:
    """
    Analyzes NSE options chain for institutional positioning.
    PCR, OI concentration, and key strike levels reveal what big money expects.
    """

    NSE_OPTIONS_URL = "https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    NSE_INDEX_URL   = "https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"

    async def analyze(self, symbol: str = "NIFTY") -> dict:
        """Full options chain analysis."""
        log = logger.bind(symbol=symbol, source="options_chain")
        log.info("options_chain.analyze")

        client       = await get_nse_client()
        options_data = None

        try:
            is_index = symbol in ("NIFTY", "BANKNIFTY", "MIDCPNIFTY", "FINNIFTY")
            url      = (self.NSE_INDEX_URL if is_index else self.NSE_OPTIONS_URL).format(symbol=symbol)
            r        = await client.get(url)
            if r.status_code == 200:
                options_data = r.json()
        except Exception as e:
            log.warning("options_chain.fetch_error", error=str(e))
        finally:
            await client.aclose()

        if not options_data:
            return self._get_fallback(symbol)

        summary = self._summarize_chain(options_data)
        if not summary:
            return self._get_fallback(symbol)

        result = await self._analyze_with_llm(symbol, summary)
        result["oi_summary"]  = summary
        result["fetched_at"]  = datetime.utcnow().isoformat()
        result["data_source"] = "NSE Options Chain"

        log.info("options_chain.complete",
                 symbol=symbol, pcr=summary.get("pcr"))
        return result

    def _summarize_chain(self, data: dict) -> Optional[dict]:
        """Extract key metrics from options chain."""
        try:
            records       = data.get("records", {})
            chain_data    = records.get("data", [])
            current_price = records.get("underlyingValue", 0)

            if not chain_data or not current_price:
                return None

            total_call_oi = 0
            total_put_oi  = 0
            strike_oi     = {}

            for item in chain_data:
                strike   = item.get("strikePrice", 0)
                ce_oi    = item.get("CE", {}).get("openInterest", 0) or 0
                pe_oi    = item.get("PE", {}).get("openInterest", 0) or 0
                total_call_oi += ce_oi
                total_put_oi  += pe_oi
                strike_oi[strike] = {"call_oi": ce_oi, "put_oi": pe_oi}

            # PCR
            pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 1.0

            # Max OI strikes
            max_call_strike = max(strike_oi.keys(),
                                  key=lambda s: strike_oi[s]["call_oi"], default=0)
            max_put_strike  = max(strike_oi.keys(),
                                  key=lambda s: strike_oi[s]["put_oi"],  default=0)

            # Near ATM strikes (within 5%)
            atm_range  = [(s, strike_oi[s]) for s in strike_oi
                          if abs(s - current_price) / current_price < 0.05]
            atm_sorted = sorted(atm_range, key=lambda x: abs(x[0] - current_price))

            return {
                "current_price":    current_price,
                "pcr":              pcr,
                "total_call_oi":    total_call_oi,
                "total_put_oi":     total_put_oi,
                "max_call_strike":  max_call_strike,
                "max_put_strike":   max_put_strike,
                "atm_strikes":      atm_sorted[:5],
            }

        except Exception as e:
            logger.warning("options_chain.summarize_error", error=str(e))
            return None

    async def _analyze_with_llm(self, symbol: str, summary: dict) -> dict:
        prompt = OPTIONS_CHAIN_PROMPT.format(
            symbol=symbol,
            current_price=summary.get("current_price", 0),
            pcr=summary.get("pcr", 1.0),
            max_call_strike=summary.get("max_call_strike", 0),
            max_put_strike=summary.get("max_put_strike",  0),
            oi_summary=json.dumps(summary, indent=2),
        )
        try:
            text = await call_llm(prompt, agent_name="market_intelligence")
            return json.loads(text)
        except Exception as e:
            logger.warning("options_chain.llm_error", error=str(e))
            return {
                "symbol":          symbol,
                "pcr":             summary.get("pcr"),
                "key_resistance":  summary.get("max_call_strike"),
                "key_support":     summary.get("max_put_strike"),
                "plain_explanation": f"PCR: {summary.get('pcr')} — Resistance: ₹{summary.get('max_call_strike')} — Support: ₹{summary.get('max_put_strike')}",
            }

    def _get_fallback(self, symbol: str) -> dict:
        return {
            "symbol":          symbol,
            "market_sentiment": "neutral",
            "plain_explanation": "Options chain data unavailable — check NSE website",
            "fetched_at":      datetime.utcnow().isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════════
# MASTER INTELLIGENCE AGGREGATOR
# Combines all 8 modules into one unified call
# ═════════════════════════════════════════════════════════════════════════════

class MarketIntelligence:
    """
    Master class combining all 8 intelligence modules.
    Called by the Orchestrator to enrich recommendations with deep market data.
    """

    def __init__(self):
        self.bulk_deals     = BulkDealMonitor()
        self.insider        = InsiderTradingMonitor()
        self.earnings       = EarningsCalendar()
        self.sector_rotation = SectorRotationModel()
        self.fii_sectoral   = FIISectoralFlowTracker()
        self.mf_tracker     = MutualFundTracker()
        self.max_pain       = MaxPainCalculator()
        self.options_chain  = OptionsChainAnalyzer()

    async def get_full_intelligence(
        self,
        symbols: list = None,
        macro_snapshot: dict = None,
        signals: list = None,
        india_vix: float = 17.0,
        risk_regime: str = "neutral",
    ) -> dict:
        """
        Run all 8 intelligence modules concurrently.
        Called once per session — results cached in Redis.
        """
        log = logger.bind(source="market_intelligence")
        log.info("market_intelligence.start", symbols=symbols)

        symbols = symbols or []

        # Run market-wide tasks concurrently
        bulk_task    = self.bulk_deals.get_today_deals()
        insider_task = self.insider.get_recent_insider_trades(days=7)
        earnings_task = self.earnings.get_upcoming_results(days_ahead=14)
        fii_task     = self.fii_sectoral.get_sectoral_flows()
        max_pain_task = self.max_pain.calculate("NIFTY")
        options_task = self.options_chain.analyze("NIFTY")
        sector_task  = self.sector_rotation.analyze(
            macro_snapshot=macro_snapshot or {},
            signals=signals or [],
            india_vix=india_vix,
            risk_regime=risk_regime,
        )

        (bulk_result, insider_result, earnings_result,
         fii_result, max_pain_result, options_result,
         sector_result) = await asyncio.gather(
            bulk_task, insider_task, earnings_task,
            fii_task, max_pain_task, options_task,
            sector_task,
            return_exceptions=True
        )

        # Per-symbol tasks (run for top 3 symbols)
        mf_results = {}
        for symbol in symbols[:3]:
            try:
                mf_results[symbol] = await self.mf_tracker.get_mf_holdings(symbol)
            except Exception as e:
                mf_results[symbol] = {"error": str(e)}

        def safe(result, fallback=None):
            return result if not isinstance(result, Exception) else (fallback or {})

        intelligence = {
            "bulk_deals":         safe(bulk_result),
            "insider_trading":    safe(insider_result),
            "earnings_calendar":  safe(earnings_result),
            "sector_rotation":    safe(sector_result),
            "fii_sectoral_flows": safe(fii_result),
            "mf_holdings":        mf_results,
            "max_pain":           safe(max_pain_result),
            "options_chain":      safe(options_result),
            "generated_at":       datetime.utcnow().isoformat(),
        }

        log.info("market_intelligence.complete")
        return intelligence

    async def get_symbol_intelligence(self, symbol: str) -> dict:
        """
        Deep intelligence for a single stock — runs relevant modules.
        Called by Company Intelligence agent per stock pick.
        """
        insider_task  = self.insider.get_symbol_insider_activity(symbol)
        earnings_task = self.earnings.check_symbol_results(symbol)
        mf_task       = self.mf_tracker.get_mf_holdings(symbol)
        bulk_task     = self.bulk_deals.get_deals_for_symbol(symbol, days=30)
        options_task  = self.options_chain.analyze(symbol)

        results = await asyncio.gather(
            insider_task, earnings_task, mf_task,
            bulk_task, options_task,
            return_exceptions=True
        )

        def safe(r):
            return r if not isinstance(r, Exception) else {}

        return {
            "symbol":           symbol,
            "insider_activity": safe(results[0]),
            "earnings_risk":    safe(results[1]),
            "mf_holdings":      safe(results[2]),
            "recent_bulk_deals": safe(results[3]) if isinstance(results[3], list) else [],
            "options_data":     safe(results[4]),
            "analyzed_at":      datetime.utcnow().isoformat(),
        }