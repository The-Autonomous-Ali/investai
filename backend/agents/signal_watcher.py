"""
Signal Watcher Agent - Monitors all sources and detects market signals.
Runs continuously in the background and also on-demand.
"""
import hashlib
import json
import feedparser
import structlog
from datetime import datetime, timedelta
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger()
client = AsyncAnthropic()

SIGNAL_CLASSIFIER_PROMPT = """You are a financial signal extractor specializing in Indian markets.

Analyze this content and extract structured signal data.

Content: {content}
Source: {source}
Source Tier: {tier}

Extract and return ONLY valid JSON (no markdown, no preamble):
{{
  "title": "concise signal title (max 100 chars)",
  "signal_type": "geopolitical|monetary|fiscal|commodity|currency|corporate|natural_disaster",
  "urgency": "breaking|developing|long_term",
  "importance_score": 0.0-10.0,
  "confidence": 0.0-1.0,
  "geography": "global|regional|india",
  "sentiment": "positive|negative|neutral",
  "entities_mentioned": ["Iran", "Oil", "RBI"],
  "sectors_affected": {{
    "aviation": "negative",
    "energy": "positive"
  }},
  "india_impact": "high|medium|low|none",
  "second_order_effects": [
    "Oil spike -> INR depreciation -> FII outflows",
    "Higher input costs -> FMCG margin pressure"
  ],
  "requires_immediate_analysis": true
}}

If the content has no meaningful financial signal for Indian markets, return:
{{"importance_score": 0, "requires_immediate_analysis": false}}
"""

RSS_SOURCES = [
    # Tier 1 - Official
    {"url": "https://rbi.org.in/scripts/rss.aspx",                                          "name": "RBI",               "tier": 1},
    {"url": "https://www.sebi.gov.in/rss/index.html",                                        "name": "SEBI",              "tier": 1},
    {"url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",                       "name": "Ministry Finance",  "tier": 1},

    # Tier 2 - Financial Media
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",          "name": "Economic Times",    "tier": 2},
    {"url": "https://www.livemint.com/rss/markets",                                          "name": "Mint Markets",      "tier": 2},
    {"url": "https://www.business-standard.com/rss/markets-106.rss",                         "name": "Business Standard", "tier": 2},
    {"url": "https://www.moneycontrol.com/rss/results.xml",                                  "name": "Moneycontrol",      "tier": 2},

    # Tier 3 - Global Context
    {"url": "https://feeds.reuters.com/reuters/businessNews",                                "name": "Reuters Business",  "tier": 3},
    {"url": "https://www.imf.org/en/News/rss?language=eng",                                  "name": "IMF",               "tier": 3},
]


class SignalWatcherAgent:
    def __init__(self, db_session: AsyncSession, redis_client):
        self.db    = db_session
        self.redis = redis_client

    async def get_current_signals(self, limit: int = 10) -> dict:
        """Get top current signals from cache or DB."""
        from models.models import Signal

        # Try cache first
        cached = await self._get_cached_signals()
        if cached:
            return cached

        # ✅ FIXED: Use async SQLAlchemy select() instead of .query()
        result = await self.db.execute(
            select(Signal)
            .where(Signal.importance_score >= 5.0)
            .where(Signal.detected_at >= datetime.utcnow() - timedelta(days=3))
            .order_by(Signal.importance_score.desc(), Signal.detected_at.desc())
            .limit(limit)
        )
        signals = result.scalars().all()

        data = {
            "signals":         [self._signal_to_dict(s) for s in signals],
            "market_snapshot": await self._get_market_snapshot(),
            "last_updated":    datetime.utcnow().isoformat(),
        }

        await self._cache_signals(data)
        return data

    async def scan_all_sources(self):
        """Full scan of all sources. Called by the background worker."""
        logger.info("signal_watcher.full_scan.start")
        new_signals = []

        for source in RSS_SOURCES:
            try:
                signals = await self._scan_rss(source)
                new_signals.extend(signals)
            except Exception as e:
                logger.warning("signal_watcher.rss_error", source=source["name"], error=str(e))

        logger.info("signal_watcher.full_scan.complete", new_signals=len(new_signals))
        return new_signals

    async def _scan_rss(self, source: dict) -> list:
        """Scan a single RSS feed and extract signals."""
        from models.models import Signal

        try:
            feed = feedparser.parse(source["url"])
        except Exception as e:
            logger.warning("rss.parse_error", url=source["url"], error=str(e))
            return []

        new_signals = []

        for entry in feed.entries[:10]:
            content      = f"{entry.get('title', '')} {entry.get('summary', '')}"
            content_hash = hashlib.md5(content.encode()).hexdigest()

            # ✅ FIXED: Async duplicate check
            result   = await self.db.execute(
                select(Signal).where(Signal.content_hash == content_hash)
            )
            existing = result.scalar_one_or_none()
            if existing:
                continue

            # Classify with Claude
            signal_data = await self._classify_signal(content, source["name"], source["tier"])
            if not signal_data or signal_data.get("importance_score", 0) < 3.0:
                continue

            signal = Signal(
                title               = signal_data.get("title", entry.get("title", ""))[:100],
                content             = content[:2000],
                source              = source["name"],
                source_agent        = "rss_agent",
                source_tier         = source["tier"],
                signal_type         = signal_data.get("signal_type", "monetary"),
                urgency             = signal_data.get("urgency", "developing"),
                importance_score    = signal_data.get("importance_score", 5.0),
                confidence          = signal_data.get("confidence", 0.5),
                geography           = signal_data.get("geography", "india"),
                sentiment           = signal_data.get("sentiment", "neutral"),
                entities_mentioned  = signal_data.get("entities_mentioned", []),
                sectors_affected    = signal_data.get("sectors_affected", {}),
                india_impact_analysis = signal_data.get("india_impact", "medium"),
                chain_effects       = signal_data.get("second_order_effects", []),
                final_weight        = signal_data.get("confidence", 0.5) * source["tier"] / 4,
                content_hash        = content_hash,
            )

            self.db.add(signal)
            new_signals.append(signal)
            logger.info("signal_watcher.new_signal", title=signal.title, source=source["name"], score=signal.importance_score)

        if new_signals:
            await self.db.commit()  # ✅ FIXED: async commit
            logger.info("signal_watcher.saved", count=len(new_signals), source=source["name"])

        return new_signals

    async def _classify_signal(self, content: str, source: str, tier: int) -> dict:
        """Use Claude Haiku to classify and extract signal data."""
        try:
            response = await client.messages.create(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 800,
                messages   = [{
                    "role":    "user",
                    "content": SIGNAL_CLASSIFIER_PROMPT.format(
                        content = content[:1500],
                        source  = source,
                        tier    = tier,
                    )
                }]
            )
            text = response.content[0].text.strip()
            return json.loads(text)
        except Exception as e:
            logger.warning("signal_classifier.error", error=str(e))
            return {}

    async def _get_market_snapshot(self) -> dict:
        """Get current market data snapshot."""
        cached = await self.redis.get("market_snapshot") if self.redis else None
        if cached:
            return json.loads(cached)

        snapshot = {
            "nifty50":     {"value": 22450.0, "change_pct": -0.42},
            "sensex":      {"value": 73900.0, "change_pct": -0.38},
            "india_vix":   {"value": 14.2,    "note": "low_fear"},
            "usd_inr":     {"value": 83.45,   "change_pct": 0.12},
            "brent_crude": {"value": 84.20,   "unit": "USD/barrel"},
            "gold_mcx":    {"value": 63450.0, "unit": "INR/10g"},
            "fii_today":   {"value": -820.0,  "unit": "crore INR"},
            "dii_today":   {"value": 1240.0,  "unit": "crore INR"},
            "timestamp":   datetime.utcnow().isoformat(),
        }

        if self.redis:
            await self.redis.setex("market_snapshot", 900, json.dumps(snapshot))

        return snapshot

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
            "entities_mentioned": signal.entities_mentioned or [],
            "sectors_affected":   signal.sectors_affected or {},
            "chain_effects":      signal.chain_effects or [],
            "stage":              signal.stage,
            "source":             signal.source,
            "detected_at":        signal.detected_at.isoformat() if signal.detected_at else None,
        }
