"""Generic RSS/Atom connector.

Configured once per feed via __init__. The `feed_registry` module holds
the full catalogue and instantiates one RSSConnector per URL.

This replaces the legacy `backend/scrapers/news_scraper.py` pattern
(single function, hardcoded feeds, in-memory dedup per run) with a
connector-per-feed design that composes with BaseConnector's
cross-process dedup and error handling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx
import feedparser
import structlog

from ingestion.base import BaseConnector, RawSignal

logger = structlog.get_logger()

# Cap entries per feed pass to avoid ingesting years of backlog on first run.
MAX_ENTRIES_PER_PASS = 25

# Cap body length to protect LLM prompt size downstream.
MAX_BODY_CHARS = 4000

DEFAULT_TIMEOUT = 15.0
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestAI/1.0; +https://investai.co.in/bot)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}


class RSSConnector(BaseConnector):
    """One instance per feed URL.

    Example:
        fed = RSSConnector(
            name="fed-monetary",
            url="https://www.federalreserve.gov/feeds/press_monetary.xml",
            region="us",
            tier=1,
            category="monetary",
        )
        await fed.run()
    """

    def __init__(
        self,
        name: str,
        url: str,
        region: str,
        tier: int,
        category: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.url = url
        self.region = region
        self.tier = tier
        self.category = category
        self._http = http_client  # injectable for tests

    async def fetch(self) -> AsyncIterator[RawSignal]:
        text = await self._fetch_feed_text()
        if not text:
            return

        parsed = feedparser.parse(text)
        entries = parsed.entries[:MAX_ENTRIES_PER_PASS]

        for entry in entries:
            try:
                signal = self._entry_to_signal(entry)
            except Exception as e:
                # One bad entry should not kill the feed pass.
                self._log.warning(
                    "rss.entry.parse_failed",
                    url=self.url,
                    error=str(e),
                )
                continue

            if signal is None:
                continue
            yield signal

    async def _fetch_feed_text(self) -> Optional[str]:
        """Pull the raw feed text. Returns None on network failure (logged)."""
        owns_client = self._http is None
        client = self._http or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )
        try:
            resp = await client.get(self.url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            self._log.warning("rss.fetch.failed", url=self.url, error=str(e))
            return None
        finally:
            if owns_client:
                await client.aclose()

    def _entry_to_signal(self, entry) -> Optional[RawSignal]:
        """Map one feedparser entry to a RawSignal. Returns None if unusable."""
        title = (entry.get("title") or "").strip()
        if not title:
            return None

        body = (
            entry.get("summary")
            or entry.get("description")
            or ""
        ).strip()[:MAX_BODY_CHARS]

        link = entry.get("link") or ""

        published_at = self._parse_published(entry)

        return RawSignal(
            source_name=self.name,
            source_region=self.region,
            source_tier=self.tier,
            category=self.category,
            url=link,
            title=title,
            body=body,
            published_at=published_at.isoformat() if published_at else None,
        )

    @staticmethod
    def _parse_published(entry) -> Optional[datetime]:
        """Extract a UTC datetime from an RSS entry, or None if unavailable."""
        candidates = (
            getattr(entry, "published_parsed", None),
            getattr(entry, "updated_parsed", None),
        )
        for parsed in candidates:
            if parsed is None:
                continue
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue
        return None
