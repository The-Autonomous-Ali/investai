"""
News Scraper — pulls headlines from Indian financial RSS feeds.

Sources (all free, no API key needed):
- Economic Times (Markets, Economy)
- Mint (Markets, Companies)
- Moneycontrol (Markets, Business)
- RBI Press Releases
- SEBI Circulars RSS
- Reuters India

Each source is scored by tier (1 = official/govt, 2 = major media, 3 = secondary).
The SignalWatcher agent processes these into structured signals.
"""
import feedparser
import hashlib
import structlog
from datetime import datetime, timezone
from typing import Optional
import httpx

logger = structlog.get_logger()

# RSS feed sources — tier 1 is most authoritative
RSS_FEEDS = [
    # Tier 1: Official / Government
    {"url": "https://www.rbi.org.in/pressreleasefeed.xml", "source": "RBI", "tier": 1, "category": "monetary"},
    {"url": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=0&smession=No&ession=No", "source": "SEBI", "tier": 1, "category": "regulatory"},

    # Tier 2: Major financial media
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "source": "Economic Times", "tier": 2, "category": "markets"},
    {"url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "source": "Economic Times", "tier": 2, "category": "economy"},
    {"url": "https://www.livemint.com/rss/markets", "source": "Mint", "tier": 2, "category": "markets"},
    {"url": "https://www.livemint.com/rss/companies", "source": "Mint", "tier": 2, "category": "corporate"},
    {"url": "https://www.moneycontrol.com/rss/MCtopnews.xml", "source": "Moneycontrol", "tier": 2, "category": "markets"},
    {"url": "https://www.moneycontrol.com/rss/business.xml", "source": "Moneycontrol", "tier": 2, "category": "corporate"},

    # Tier 3: Secondary / Global context
    {"url": "https://news.google.com/rss/search?q=india+economy+market&hl=en-IN&gl=IN&ceid=IN:en", "source": "Google News", "tier": 3, "category": "general"},
    {"url": "https://feeds.feedburner.com/ndtvprofit-latest", "source": "NDTV Profit", "tier": 3, "category": "markets"},
]


async def scrape_all_feeds() -> list[dict]:
    """
    Scrape all RSS feeds and return deduplicated articles.
    Returns list of dicts with: title, content, source, source_tier, category, url, published_at, content_hash
    """
    all_articles = []

    for feed_config in RSS_FEEDS:
        try:
            articles = await _scrape_single_feed(feed_config)
            all_articles.extend(articles)
            logger.info("scraper.feed.success", source=feed_config["source"], articles=len(articles))
        except Exception as e:
            logger.warning("scraper.feed.error", source=feed_config["source"], error=str(e))
            continue

    # Deduplicate by content hash
    seen_hashes = set()
    unique = []
    for article in all_articles:
        if article["content_hash"] not in seen_hashes:
            seen_hashes.add(article["content_hash"])
            unique.append(article)

    logger.info("scraper.complete", total=len(all_articles), unique=len(unique))
    return unique


async def _scrape_single_feed(feed_config: dict) -> list[dict]:
    """Parse a single RSS feed and return structured articles."""
    articles = []

    # feedparser is synchronous — use httpx to fetch, then parse
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(feed_config["url"], follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("scraper.fetch.error", url=feed_config["url"], error=str(e))
            return []

    feed = feedparser.parse(resp.text)

    for entry in feed.entries[:15]:  # Max 15 per feed to avoid noise
        title = entry.get("title", "").strip()
        if not title:
            continue

        summary = entry.get("summary", entry.get("description", "")).strip()
        link = entry.get("link", "")

        # Parse publish date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_at = datetime.now(timezone.utc)
        else:
            published_at = datetime.now(timezone.utc)

        # Content hash for deduplication
        content_hash = hashlib.md5(f"{title}{link}".encode()).hexdigest()

        articles.append({
            "title": title,
            "content": summary[:2000],  # Limit content size
            "source": feed_config["source"],
            "source_tier": feed_config["tier"],
            "category": feed_config["category"],
            "url": link,
            "published_at": published_at,
            "content_hash": content_hash,
        })

    return articles


async def scrape_feed_by_source(source_name: str) -> list[dict]:
    """Scrape feeds from a specific source only."""
    feeds = [f for f in RSS_FEEDS if f["source"].lower() == source_name.lower()]
    articles = []
    for feed_config in feeds:
        try:
            result = await _scrape_single_feed(feed_config)
            articles.extend(result)
        except Exception as e:
            logger.warning("scraper.source.error", source=source_name, error=str(e))
    return articles
