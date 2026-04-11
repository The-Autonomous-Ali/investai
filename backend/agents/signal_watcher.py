"""
Signal Watcher Agent - Monitors all sources and detects market signals.
UPDATED: Live market data from Yahoo Finance — replaces stale mock prices.
"""
import hashlib
import json
import feedparser
import structlog
from datetime import datetime, timedelta
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from utils.llm_client import call_llm
from agents.credibility_engine import CredibilityEngine
from agents.graphrag_enricher import GraphRAGEnricher

logger = structlog.get_logger()

SIGNAL_CLASSIFIER_PROMPT = """You are a financial signal extractor specializing in Indian markets.

Analyze this content and extract structured signal data.

Content: {content}
Source: {source}
Source Tier: {tier}
Source Region: {region}

Extract and return ONLY valid JSON (no markdown, no preamble):
{{
  "title": "concise signal title (max 100 chars)",
  "signal_type": "geopolitical|monetary|fiscal|commodity|currency|corporate|natural_disaster|trade",
  "urgency": "breaking|developing|long_term",
  "importance_score": 0.0-10.0,
  "confidence": 0.0-1.0,
  "geography": "global|regional|india|us|europe|china|middle_east",
  "sentiment": "positive|negative|neutral",
  "claim_type": "factual|analysis|opinion|tip",
  "entities_mentioned": ["Fed", "Oil", "RBI"],
  "sectors_affected": {{
    "aviation": "negative",
    "energy": "positive"
  }},
  "india_impact": "high|medium|low|none",
  "india_impact_reasoning": "Why this affects India specifically",
  "second_order_effects": [
    "Oil spike -> INR depreciation -> FII outflows",
    "Higher input costs -> FMCG margin pressure"
  ],
  "root_cause": {{
    "trigger_event": "What specific public event/decision triggered this signal?",
    "trigger_source": "Reuters|RBI|OPEC|etc — who reported or announced it",
    "trigger_date": "YYYY-MM-DD or best estimate",
    "trigger_category": "geopolitical|monetary|fiscal|commodity|currency|corporate|natural_disaster|trade"
  }},
  "requires_immediate_analysis": true
}}

claim_type legend (be strict — this decides if the signal survives credibility filtering):
- factual: Verifiable event, decision, or data point (e.g. "RBI raised repo rate to 6.5%", "Brent closed at $92")
- analysis: Informed reasoning about a factual event (e.g. "The hike is likely to slow FMCG demand")
- opinion: Subjective view without strong evidence ("Markets look overvalued to me")
- tip: Trading tip, target price, buy/sell recommendation — ALWAYS use this for pump/dump content

If content has no meaningful financial signal for Indian markets, return:
{{"importance_score": 0, "requires_immediate_analysis": false}}
"""

VALID_SIGNAL_TYPES = {
    "geopolitical", "monetary", "fiscal", "commodity",
    "currency", "corporate", "natural_disaster", "trade"
}

# ── RSS Sources — Global + India ──────────────────────────────────────────────

RSS_SOURCES = [
    # ── TIER 1: Central Banks & Regulators ───────────────────────────────────
    {"url": "https://www.federalreserve.gov/feeds/press_all.xml",                        "name": "US Federal Reserve",     "tier": 1, "region": "us"},
    {"url": "https://www.ecb.europa.eu/rss/press.html",                                  "name": "European Central Bank",  "tier": 1, "region": "europe"},
    {"url": "https://rbi.org.in/scripts/rss.aspx",                                       "name": "RBI",                    "tier": 1, "region": "india"},
    {"url": "https://www.sebi.gov.in/rss/index.html",                                    "name": "SEBI",                   "tier": 1, "region": "india"},
    {"url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",                   "name": "Ministry of Finance",    "tier": 1, "region": "india"},
    {"url": "https://www.imf.org/en/News/rss?language=eng",                              "name": "IMF",                    "tier": 1, "region": "global"},
    {"url": "https://www.worldbank.org/en/news/rss",                                     "name": "World Bank",             "tier": 1, "region": "global"},
    {"url": "https://www.opec.org/opec_web/en/press_room/rss.htm",                      "name": "OPEC",                   "tier": 1, "region": "middle_east"},

    # ── TIER 2: Major Global News ─────────────────────────────────────────────
    {"url": "https://feeds.reuters.com/reuters/businessNews",                            "name": "Reuters Business",       "tier": 2, "region": "global"},
    {"url": "https://feeds.reuters.com/reuters/topNews",                                 "name": "Reuters Top News",       "tier": 2, "region": "global"},
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml",                           "name": "BBC Business",           "tier": 2, "region": "global"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",                "name": "NYT Business",           "tier": 2, "region": "us"},
    {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                            "name": "Wall Street Journal",    "tier": 2, "region": "us"},

    # ── TIER 2: India Financial Media ─────────────────────────────────────────
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",      "name": "Economic Times Markets", "tier": 2, "region": "india"},
    {"url": "https://economictimes.indiatimes.com/economy/rssfeeds/1373380680.cms",      "name": "Economic Times Economy", "tier": 2, "region": "india"},
    {"url": "https://www.livemint.com/rss/markets",                                      "name": "Mint Markets",           "tier": 2, "region": "india"},
    {"url": "https://www.livemint.com/rss/economy",                                      "name": "Mint Economy",           "tier": 2, "region": "india"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss",                     "name": "Business Standard",      "tier": 2, "region": "india"},
    {"url": "https://www.moneycontrol.com/rss/results.xml",                              "name": "Moneycontrol",           "tier": 2, "region": "india"},
    {"url": "https://www.financialexpress.com/market/feed/",                             "name": "Financial Express",      "tier": 2, "region": "india"},

    # ── TIER 3: Regional & Commodity Sources ──────────────────────────────────
    {"url": "https://oilprice.com/rss/main",                                             "name": "OilPrice.com",           "tier": 3, "region": "global"},
    {"url": "https://www.mining.com/feed/",                                              "name": "Mining.com",             "tier": 3, "region": "global"},
    {"url": "https://www.scmp.com/rss/5/feed",                                           "name": "SCMP China Business",    "tier": 3, "region": "china"},
    {"url": "https://japannews.yomiuri.co.jp/feed/",                                     "name": "Japan News",             "tier": 3, "region": "japan"},
    {"url": "https://www.arabianbusiness.com/rss",                                       "name": "Arabian Business",       "tier": 3, "region": "middle_east"},
    {"url": "https://www.thehindubusinessline.com/markets/feeder/default.rss",           "name": "Hindu BusinessLine",     "tier": 3, "region": "india"},
]

# ── Yahoo Finance symbol mapping ──────────────────────────────────────────────
YAHOO_SYMBOLS = {
    "nifty50":      "^NSEI",
    "sensex":       "^BSESN",
    "india_vix":    "^INDIAVIX",
    "usd_inr":      "USDINR=X",
    "brent_crude":  "BZ=F",
    "wti_crude":    "CL=F",
    "gold_spot":    "GC=F",
    "silver_spot":  "SI=F",
    "natural_gas":  "NG=F",
    "us_10y_yield": "^TNX",
    "us_2y_yield":  "^IRX",
    "dxy":          "DX-Y.NYB",
    "vix_us":       "^VIX",
    "sp500":        "^GSPC",
    "nasdaq":       "^IXIC",
    "ftse100":      "^ISF.L",
    "dax":          "^GDAXI",
    "nikkei":       "^N225",
    "hang_seng":    "^HSI",
    "china_csi300": "000300.SS",
}

SNAPSHOT_LABELS = {
    "nifty50":      {"unit": "INR points"},
    "sensex":       {"unit": "INR points"},
    "india_vix":    {"note": "India fear index — above 20 = high fear"},
    "usd_inr":      {"note": "INR per USD — higher = weaker rupee"},
    "brent_crude":  {"unit": "USD/barrel"},
    "wti_crude":    {"unit": "USD/barrel"},
    "gold_spot":    {"unit": "USD/oz"},
    "silver_spot":  {"unit": "USD/oz"},
    "natural_gas":  {"unit": "USD/MMBtu"},
    "us_10y_yield": {"unit": "%", "note": "above 4.5% = FII outflow pressure on India"},
    "us_2y_yield":  {"unit": "%"},
    "dxy":          {"note": "strong dollar = INR pressure + FII outflows"},
    "vix_us":       {"note": "US fear index — above 20 = risk-off globally"},
    "sp500":        {"unit": "USD points"},
    "nasdaq":       {"unit": "USD points"},
    "ftse100":      {"unit": "GBP points"},
    "dax":          {"unit": "EUR points"},
    "nikkei":       {"unit": "JPY points"},
    "hang_seng":    {"unit": "HKD points"},
    "china_csi300": {"unit": "CNY points"},
}


class SignalWatcherAgent:
    def __init__(self, db_session: AsyncSession, redis_client, neo4j_driver=None):
        self.db          = db_session
        self.redis       = redis_client
        self.neo4j       = neo4j_driver
        self.credibility = CredibilityEngine()
        # Enricher only active when a real Neo4j driver is passed.
        self.enricher    = GraphRAGEnricher(neo4j_driver) if neo4j_driver else None

    async def get_current_signals(self, limit: int = 15) -> dict:
        """Get top current signals from cache or DB."""
        from models.models import Signal

        cached = await self._get_cached_signals()
        if cached:
            return cached

        result = await self.db.execute(
            select(Signal)
            .where(Signal.importance_score >= 5.0)
            .where(Signal.detected_at >= datetime.utcnow() - timedelta(days=3))
            .order_by(Signal.importance_score.desc(), Signal.detected_at.desc())
            .limit(limit)
        )
        signals = result.scalars().all()

        if not signals:
            return await self._get_mock_signals_with_live_prices()

        data = {
            "signals":         [self._signal_to_dict(s) for s in signals],
            "market_snapshot": await self._get_market_snapshot(),
            "last_updated":    datetime.utcnow().isoformat(),
        }

        await self._cache_signals(data)
        return data

    async def _get_mock_signals_with_live_prices(self) -> dict:
        """Mock signals but with LIVE prices from Yahoo Finance."""
        live_snapshot = await self._get_market_snapshot()

        brent_price = live_snapshot.get("brent_crude", {}).get("value", 84)
        brent_title = f"Brent Crude at ${brent_price:.0f} — Middle East Tensions Continue"

        india_vix = live_snapshot.get("india_vix", {}).get("value", 14)
        vix_note  = "high_fear" if india_vix > 20 else "moderate_fear" if india_vix > 15 else "low_fear"

        return {
            "signals": [
                {
                    "id": "mock_1",
                    "title": brent_title,
                    "signal_type": "commodity",
                    "urgency": "breaking" if brent_price > 95 else "developing",
                    "importance_score": 9.1 if brent_price > 95 else 7.5,
                    "confidence": 0.85,
                    "sentiment": "negative",
                    "geography": "middle_east",
                    "entities_mentioned": ["Oil", "Middle East", "OPEC"],
                    "sectors_affected": {"aviation": "negative", "energy": "positive", "paints": "negative"},
                    "chain_effects": ["Oil spike -> CAD widening", "INR depreciation -> FII outflows"],
                    "india_impact": "high",
                    "stage": "ESCALATING",
                    "source": "Live Price Feed",
                    "detected_at": datetime.utcnow().isoformat(),
                    "is_mock": True
                },
                {
                    "id": "mock_2",
                    "title": "US Federal Reserve Signals Rates Higher for Longer",
                    "signal_type": "monetary",
                    "urgency": "developing",
                    "importance_score": 9.3,
                    "confidence": 0.91,
                    "sentiment": "negative",
                    "geography": "us",
                    "entities_mentioned": ["Federal Reserve", "USD", "US Treasuries"],
                    "sectors_affected": {"banking": "negative", "it": "negative", "gold": "positive"},
                    "chain_effects": ["Fed hawkish -> DXY strengthens -> FII outflows from India"],
                    "india_impact": "high",
                    "stage": "DEVELOPING",
                    "source": "Mock Engine",
                    "detected_at": datetime.utcnow().isoformat(),
                    "is_mock": True
                },
                {
                    "id": "mock_3",
                    "title": "RBI Governor: Vigilant on Inflation, Committed to 4% Target",
                    "signal_type": "monetary",
                    "urgency": "developing",
                    "importance_score": 8.8,
                    "confidence": 0.92,
                    "sentiment": "neutral",
                    "geography": "india",
                    "entities_mentioned": ["RBI", "Inflation", "Repo Rate"],
                    "sectors_affected": {"banking": "positive", "real_estate": "neutral"},
                    "chain_effects": ["Rate hold likely -> Banking NIM stable"],
                    "india_impact": "high",
                    "stage": "ACTIVE",
                    "source": "Mock Engine",
                    "detected_at": datetime.utcnow().isoformat(),
                    "is_mock": True
                },
                {
                    "id": "mock_4",
                    "title": "China PMI Contracts for Third Consecutive Month",
                    "signal_type": "trade",
                    "urgency": "developing",
                    "importance_score": 7.8,
                    "confidence": 0.88,
                    "sentiment": "negative",
                    "geography": "china",
                    "entities_mentioned": ["China", "PMI", "Manufacturing"],
                    "sectors_affected": {"metals": "negative", "commodities": "negative"},
                    "chain_effects": ["China slowdown -> Commodity demand drop -> India steel sector pressure"],
                    "india_impact": "medium",
                    "stage": "DEVELOPING",
                    "source": "Mock Engine",
                    "detected_at": datetime.utcnow().isoformat(),
                    "is_mock": True
                },
            ],
            "market_snapshot": live_snapshot,
            "last_updated": datetime.utcnow().isoformat(),
            "note": f"Demo Mode: Mock signals with LIVE market prices. India VIX: {india_vix:.1f} ({vix_note})",
        }

    async def scan_all_sources(self, tier_filter: int | None = None, max_entries_per_feed: int = 10):
        """Full scan of RSS sources.

        Args:
            tier_filter: If set, only scan sources whose tier == this value.
                         E.g. tier_filter=1 scans only central banks & regulators.
            max_entries_per_feed: Hard cap on how many entries per feed are
                                  classified. Used by the Phase 1 CLI to keep
                                  Kaggle Ollama load bounded.
        """
        sources = [s for s in RSS_SOURCES if tier_filter is None or s["tier"] == tier_filter]
        logger.info("signal_watcher.full_scan.start",
                    total_sources=len(sources),
                    tier_filter=tier_filter,
                    max_entries_per_feed=max_entries_per_feed)
        new_signals = []

        for source in sources:
            try:
                signals = await self._scan_rss(source, max_entries=max_entries_per_feed)
                new_signals.extend(signals)
            except Exception as e:
                logger.warning("signal_watcher.rss_error", source=source["name"], error=str(e))

        logger.info("signal_watcher.full_scan.complete", new_signals=len(new_signals))
        return new_signals

    async def _scan_rss(self, source: dict, max_entries: int = 10) -> list:
        from models.models import Signal

        try:
            feed = feedparser.parse(source["url"])
        except Exception as e:
            logger.warning("rss.parse_error", url=source["url"], error=str(e))
            return []

        new_signals = []

        for entry in feed.entries[:max_entries]:
            content      = f"{entry.get('title', '')} {entry.get('summary', '')}"
            content_hash = hashlib.md5(content.encode()).hexdigest()

            try:
                result   = await self.db.execute(
                    select(Signal).where(Signal.content_hash == content_hash)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    continue

                signal_data = await self._classify_signal(
                    content, source["name"], source["tier"], source.get("region", "global")
                )
                if not signal_data or signal_data.get("importance_score", 0) < 3.0:
                    continue

                # FIX: Sanitize signal_type — if AI returns an invalid value,
                # fall back to "monetary" instead of crashing the whole session
                raw_type = signal_data.get("signal_type", "monetary")
                safe_type = raw_type if raw_type in VALID_SIGNAL_TYPES else "monetary"

                # ── Credibility gate ────────────────────────────────────────
                # Phase 1: corroboration_count defaults to 1 (self-only).
                # Future work: lookup recent similar signals for true corroboration.
                claim_type = signal_data.get("claim_type", "analysis")
                credibility_score = self.credibility.compute_credibility(
                    source_name=source["name"],
                    tier=source["tier"],
                    claim_type=claim_type,
                    corroboration_count=1,
                )
                if not self.credibility.passes_threshold(credibility_score):
                    logger.info("signal_watcher.credibility_rejected",
                                source=source["name"],
                                credibility=credibility_score,
                                claim_type=claim_type,
                                tier=source["tier"])
                    continue

                # Extract root cause from LLM response (0 extra calls)
                root_cause_raw = signal_data.get("root_cause", {})
                source_url = entry.get("link", "")
                root_cause_chain = []
                if root_cause_raw and root_cause_raw.get("trigger_event"):
                    root_cause_chain = [{
                        "event":      root_cause_raw.get("trigger_event", ""),
                        "source":     root_cause_raw.get("trigger_source", source["name"]),
                        "date":       root_cause_raw.get("trigger_date", ""),
                        "source_url": source_url,
                        "role":       "trigger",
                    }]

                signal = Signal(
                    title                 = signal_data.get("title", entry.get("title", ""))[:100],
                    content               = content[:2000],
                    source                = source["name"],
                    source_agent          = "rss_agent",
                    source_tier           = source["tier"],
                    signal_type           = safe_type,
                    urgency               = signal_data.get("urgency", "developing"),
                    importance_score      = signal_data.get("importance_score", 5.0),
                    confidence            = signal_data.get("confidence", 0.5),
                    geography             = signal_data.get("geography", "global"),
                    sentiment             = signal_data.get("sentiment", "neutral"),
                    entities_mentioned    = signal_data.get("entities_mentioned", []),
                    sectors_affected      = signal_data.get("sectors_affected", {}),
                    india_impact_analysis = signal_data.get("india_impact", "medium"),
                    chain_effects         = signal_data.get("second_order_effects", []),
                    root_cause_chain      = root_cause_chain,
                    final_weight          = signal_data.get("confidence", 0.5) * source["tier"] / 4,
                    content_hash          = content_hash,
                    # Credibility columns (005_credibility_scoring migration)
                    credibility_score     = credibility_score,
                    claim_type            = claim_type,
                    source_urls           = [source_url] if source_url else [],
                    corroboration_count   = 1,
                )

                self.db.add(signal)
                await self.db.flush()  # FIX: flush per signal so errors don't poison the whole session
                new_signals.append(signal)
                logger.info("signal_watcher.new_signal",
                            title=signal.title, source=source["name"],
                            score=signal.importance_score, region=source.get("region"))

            except Exception as e:
                # FIX: rollback after each bad signal so the session stays alive for the next one
                await self.db.rollback()
                logger.warning("signal_watcher.signal_skipped",
                               source=source["name"], error=str(e))
                continue

        if new_signals:
            try:
                await self.db.commit()
                logger.info("signal_watcher.saved", count=len(new_signals), source=source["name"])
            except Exception as e:
                await self.db.rollback()
                logger.warning("signal_watcher.commit_failed", source=source["name"], error=str(e))
                return new_signals

            # ── Graph enrichment ──────────────────────────────────────────
            # Runs AFTER Postgres commit so a Neo4j failure cannot roll back
            # signals. Each enrichment is 1 LLM call + several Cypher MERGEs.
            # Runs serially because Kaggle Ollama is single-GPU; parallelism
            # would just queue at the model layer and increase wall time.
            if self.enricher:
                today = datetime.utcnow().strftime("%Y-%m-%d")
                for signal in new_signals:
                    try:
                        # Prefer the DB-assigned detected_at if the session has
                        # already loaded the server default, else fall back to
                        # today's date — enrichment only cares about day-level
                        # granularity for timeline ordering.
                        date_str = today
                        if signal.detected_at is not None:
                            date_str = signal.detected_at.strftime("%Y-%m-%d")
                        await self.enricher.enrich_from_article(
                            article_text=signal.content or signal.title,
                            source=signal.source,
                            date=date_str,
                        )
                    except Exception as e:
                        logger.warning("signal_watcher.enrichment_failed",
                                       signal_id=getattr(signal, "id", None),
                                       source=signal.source,
                                       error=str(e))

        return new_signals

    async def _classify_signal(self, content: str, source: str, tier: int, region: str = "global") -> dict:
        prompt = SIGNAL_CLASSIFIER_PROMPT.format(
            content=content[:1500],
            source=source,
            tier=tier,
            region=region,
        )
        try:
            text = await call_llm(prompt, agent_name="signal_watcher")
            return json.loads(text)
        except Exception as e:
            logger.warning("signal_classifier.error", error=str(e))
            return {}

    # ── LIVE MARKET DATA — Yahoo Finance (free, no API key) ───────────────────

    async def _fetch_yahoo_price(self, symbol: str) -> float | None:
        """Fetch single price from Yahoo Finance."""
        try:
            import httpx
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(timeout=8) as client:
                r    = await client.get(url, headers=headers)
                data = r.json()
                return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        except Exception:
            return None

    async def _get_live_snapshot(self) -> dict:
        import asyncio

        async def fetch_one(key: str, symbol: str) -> tuple:
            price = await self._fetch_yahoo_price(symbol)
            return key, price

        tasks   = [fetch_one(k, s) for k, s in YAHOO_SYMBOLS.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        snapshot = {}
        failed   = []

        for result in results:
            if isinstance(result, Exception):
                continue
            key, price = result
            if price is not None:
                label = SNAPSHOT_LABELS.get(key, {})
                snapshot[key] = {"value": round(price, 2), **label}
            else:
                failed.append(key)

        if failed:
            logger.warning("market_snapshot.fetch_failed", symbols=failed)

        snapshot["timestamp"]      = datetime.utcnow().isoformat()
        snapshot["data_source"]    = "Yahoo Finance (live)"
        snapshot["fetch_failures"] = failed
        snapshot["fii_today"]      = {"value": None, "unit": "crore INR", "note": "NSE API needed for live FII data"}
        snapshot["dii_today"]      = {"value": None, "unit": "crore INR", "note": "NSE API needed for live DII data"}

        return snapshot

    async def _get_market_snapshot(self) -> dict:
        cached = await self.redis.get("market_snapshot") if self.redis else None
        if cached:
            return json.loads(cached)

        logger.info("market_snapshot.fetching_live")
        try:
            snapshot = await self._get_live_snapshot()
            critical = ["nifty50", "brent_crude", "usd_inr", "us_10y_yield"]
            got = [k for k in critical if snapshot.get(k, {}).get("value") is not None]

            if len(got) >= 2:
                logger.info("market_snapshot.live_success",
                            fields_fetched=len([k for k, v in snapshot.items()
                                              if isinstance(v, dict) and v.get("value") is not None]))
                if self.redis:
                    await self.redis.setex("market_snapshot", 900, json.dumps(snapshot))
                return snapshot
            else:
                logger.warning("market_snapshot.live_insufficient", got=got)
                raise Exception("Insufficient live data")

        except Exception as e:
            logger.warning("market_snapshot.live_failed_using_fallback", error=str(e))
            return self._get_fallback_snapshot()

    def _get_fallback_snapshot(self) -> dict:
        return {
            "nifty50":          {"value": 23581.0,  "note": "ESTIMATE — live fetch failed"},
            "sensex":           {"value": 76070.0,  "note": "ESTIMATE — live fetch failed"},
            "india_vix":        {"value": 19.8,     "note": "ESTIMATE — live fetch failed"},
            "usd_inr":          {"value": 92.42,    "note": "ESTIMATE — live fetch failed"},
            "brent_crude":      {"value": 103.0,    "unit": "USD/barrel", "note": "ESTIMATE"},
            "wti_crude":        {"value": 99.5,     "unit": "USD/barrel", "note": "ESTIMATE"},
            "gold_spot":        {"value": 3000.0,   "unit": "USD/oz",     "note": "ESTIMATE"},
            "silver_spot":      {"value": 34.0,     "unit": "USD/oz",     "note": "ESTIMATE"},
            "natural_gas":      {"value": 4.1,      "unit": "USD/MMBtu",  "note": "ESTIMATE"},
            "us_10y_yield":     {"value": 4.31,     "unit": "%",          "note": "ESTIMATE"},
            "dxy":              {"value": 103.5,    "note": "ESTIMATE"},
            "vix_us":           {"value": 21.0,     "note": "ESTIMATE"},
            "sp500":            {"value": 5580.0,   "note": "ESTIMATE"},
            "nasdaq":           {"value": 17500.0,  "note": "ESTIMATE"},
            "fii_today":        {"value": None,     "unit": "crore INR"},
            "dii_today":        {"value": None,     "unit": "crore INR"},
            "timestamp":        datetime.utcnow().isoformat(),
            "data_source":      "Fallback estimates — Yahoo Finance unreachable",
        }

    async def _get_cached_signals(self):
        if not self.redis:
            return None
        cached = await self.redis.get("top_signals")
        return json.loads(cached) if cached else None

    async def _cache_signals(self, data: dict):
        if self.redis:
            await self.redis.setex("top_signals", 900, json.dumps(data))

    def _signal_to_dict(self, signal) -> dict:
        return {
            "id":                 signal.id,
            "title":              signal.title,
            "signal_type":        signal.signal_type,
            "urgency":            signal.urgency,
            "importance_score":   signal.importance_score,
            "confidence":         signal.confidence,
            "sentiment":          signal.sentiment,
            "geography":          getattr(signal, "geography", "global"),
            "entities_mentioned": signal.entities_mentioned or [],
            "sectors_affected":   signal.sectors_affected or {},
            "chain_effects":      signal.chain_effects or [],
            "stage":              signal.stage,
            "source":             signal.source,
            "detected_at":        signal.detected_at.isoformat() if signal.detected_at else None,
        }