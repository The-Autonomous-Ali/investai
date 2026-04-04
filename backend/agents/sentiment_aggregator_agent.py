"""
Sentiment Aggregator Agent — Layer 3 of the data intelligence architecture.

For each company identified by Company Intelligence Agent, aggregates:
- News article sentiment
- Twitter/X mention sentiment
- Analyst upgrade/downgrade signals
- Earnings call tone analysis
- Reddit/StockTwits discussion sentiment

Produces a single SENTIMENT SCORE per company that feeds into
Company Intelligence to validate or challenge fundamental picks.
"""
import json
import structlog
from datetime import datetime

from utils.llm_client import call_llm

logger = structlog.get_logger()

SENTIMENT_ANALYSIS_PROMPT = """You are a market sentiment analyst for Indian stocks.

Analyze the following data for {company_name} ({nse_symbol}) and produce a comprehensive sentiment score.

RECENT NEWS HEADLINES: {news_headlines}
ANALYST ACTIONS (last 30 days): {analyst_actions}
SOCIAL MEDIA MENTIONS: {social_mentions}
EARNINGS TRANSCRIPT TONE: {earnings_tone}
CURRENT FUNDAMENTALS: {fundamentals}
GLOBAL CONTEXT: {global_context}

Produce a thorough sentiment analysis. Return ONLY valid JSON:
{{
  "company": "{company_name}",
  "symbol": "{nse_symbol}",
  "overall_sentiment_score": -1.0 to +1.0,
  "sentiment_label": "very_bullish|bullish|neutral|bearish|very_bearish",
  "confidence": 0.0-1.0,
  "sentiment_breakdown": {{
    "news_sentiment": -1.0 to +1.0,
    "analyst_sentiment": -1.0 to +1.0,
    "social_sentiment": -1.0 to +1.0,
    "earnings_tone": -1.0 to +1.0,
    "fundamental_momentum": -1.0 to +1.0
  }},
  "key_positive_signals": [
    "Analyst upgrades from 3 major brokerages this month",
    "Management guided 25% revenue growth in Q3 call"
  ],
  "key_negative_signals": [
    "Promoter reduced stake by 2% last week",
    "Input costs rising — margin compression likely"
  ],
  "red_flags": [
    "Promoter pledge increased to 45% — liquidity risk",
    "CFO resigned last month"
  ],
  "smart_money_signals": [
    "FII increased stake from 18% to 22% in last quarter",
    "Bulk deal: SBI Mutual Fund bought 0.5% stake"
  ],
  "narrative_summary": "2-3 sentence summary of what the market is saying about this stock",
  "sentiment_vs_fundamentals": "aligned|diverging_bullish|diverging_bearish",
  "divergence_opportunity": "Is there a mispricing? e.g. Sentiment bearish but fundamentals strong = buy opportunity",
  "momentum": "accelerating|decelerating|stable",
  "upcoming_catalysts": [
    {{"event": "Q3 earnings", "date": "2 weeks", "expected_impact": "positive"}},
    {{"event": "RBI policy", "date": "1 month", "expected_impact": "neutral"}}
  ]
}}
"""

BATCH_SENTIMENT_PROMPT = """You are a market sentiment analyst for Indian stocks.

Quickly score sentiment for multiple stocks based on current market context.

STOCKS TO SCORE: {stocks}
CURRENT MARKET ENVIRONMENT: {market_context}
RECENT SECTOR NEWS: {sector_news}

For each stock, provide a quick sentiment assessment. Return ONLY valid JSON:
{{
  "sentiments": [
    {{
      "symbol": "ONGC",
      "sentiment_score": 0.7,
      "label": "bullish",
      "one_line_reason": "Oil price spike directly benefits upstream producer",
      "risk": "Government price cap could limit upside"
    }}
  ],
  "sector_sentiment": {{
    "Oil & Gas": "bullish",
    "Aviation": "bearish",
    "IT": "neutral"
  }},
  "market_mood": "risk_on|risk_off|mixed"
}}
"""


class SentimentAggregatorAgent:
    """
    Aggregates multi-source sentiment for specific companies.
    Runs after Company Intelligence identifies target companies.
    Validates fundamental picks with market mood data.
    """

    def __init__(self, db_session=None, redis_client=None):
        self.db    = db_session
        self.redis = redis_client

    async def analyze_company(
        self,
        company_name: str,
        nse_symbol: str,
        fundamentals: dict,
        global_context: dict,
    ) -> dict:
        """Deep sentiment analysis for a single company."""
        log = logger.bind(company=nse_symbol)
        log.info("sentiment_aggregator.analyze_company")

        # In production: fetch real news, analyst reports, social data
        # For now: use AI to simulate based on company + market context
        news_headlines  = await self._fetch_news_headlines(nse_symbol)
        analyst_actions = await self._fetch_analyst_actions(nse_symbol)
        social_mentions = await self._fetch_social_mentions(nse_symbol)
        earnings_tone   = await self._fetch_earnings_tone(nse_symbol)

        prompt = SENTIMENT_ANALYSIS_PROMPT.format(
            company_name=company_name,
            nse_symbol=nse_symbol,
            news_headlines=json.dumps(news_headlines, indent=2),
            analyst_actions=json.dumps(analyst_actions, indent=2),
            social_mentions=json.dumps(social_mentions, indent=2),
            earnings_tone=json.dumps(earnings_tone, indent=2),
            fundamentals=json.dumps(fundamentals, indent=2),
            global_context=json.dumps(global_context, indent=2)[:500],
        )

        text = await call_llm(prompt, agent_name="sentiment_aggregator")
        result = json.loads(text)

        log.info("sentiment_aggregator.complete",
                 score=result.get("overall_sentiment_score"),
                 label=result.get("sentiment_label"))
        return result

    async def batch_score(
        self,
        stocks: list,
        market_context: dict,
        sector_signals: list,
    ) -> dict:
        """
        Fast batch sentiment scoring for multiple stocks.
        Used when Company Intelligence returns a list of picks.
        """
        if not stocks:
            return {"sentiments": [], "sector_sentiment": {}, "market_mood": "neutral"}

        log = logger.bind(stock_count=len(stocks))
        log.info("sentiment_aggregator.batch_score")

        sector_news = [
            {"title": s.get("title"), "type": s.get("signal_type"), "sectors": s.get("sectors_affected")}
            for s in sector_signals[:5]
        ]

        prompt = BATCH_SENTIMENT_PROMPT.format(
            stocks=json.dumps([
                {"symbol": s.get("nse_symbol", s.get("symbol", "")),
                 "name": s.get("name", ""),
                 "sector": s.get("sector", ""),
                 "fundamentals": {"pe": s.get("pe"), "growth": s.get("revenue_growth")}}
                for s in stocks[:10]
            ], indent=2),
            market_context=json.dumps({
                k: v for k, v in market_context.items()
                if k in ["us_10y_yield", "dxy", "brent_crude", "india_vix", "fii_today"]
            }, indent=2),
            sector_news=json.dumps(sector_news, indent=2),
        )

        text = await call_llm(prompt, agent_name="sentiment_aggregator")
        result = json.loads(text)

        log.info("sentiment_aggregator.batch_complete",
                 stocks_scored=len(result.get("sentiments", [])))
        return result

    # ── Data Fetchers (stub → replace with real APIs in production) ───────────

    async def _fetch_news_headlines(self, symbol: str) -> list:
        """
        Production: Use NewsAPI, Economic Times API, or Tickertape.
        For now returns structured placeholder.
        """
        return [
            f"Recent news for {symbol} — fetched from Economic Times, Mint, Business Standard",
            f"Analyst coverage and price target updates for {symbol}",
        ]

    async def _fetch_analyst_actions(self, symbol: str) -> list:
        """
        Production: Use Tickertape API or scrape broker research portals.
        """
        return [
            {"broker": "ICICI Securities", "action": "Buy", "target": "N/A", "date": "last 30 days"},
            {"broker": "Motilal Oswal",    "action": "Neutral", "target": "N/A", "date": "last 30 days"},
        ]

    async def _fetch_social_mentions(self, symbol: str) -> dict:
        """
        Production: Twitter/X API, StockTwits API, Reddit scraper.
        """
        return {
            "twitter_mention_count_7d": "moderate",
            "twitter_sentiment":        "neutral",
            "reddit_mentions":          "low",
            "stocktwits_sentiment":     "neutral",
        }

    async def _fetch_earnings_tone(self, symbol: str) -> dict:
        """
        Production: Fetch latest earnings call transcript from BSE,
        run NLP tone analysis on management commentary.
        """
        return {
            "last_earnings_call": "Q2 FY25",
            "management_tone":    "cautiously_optimistic",
            "guidance_revision":  "maintained",
            "key_management_quotes": [
                "We are confident of achieving our targets",
                "Input cost pressures are stabilizing",
            ],
        }