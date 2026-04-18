"""Generic HTML-scrape connector base.

For sources that don't publish RSS/JSON (NSDL FPI flows, PBOC English
press releases, Drewry WCI index, Baltic Dry index pages, Trading
Economics tables). Subclasses provide a `parse_html()` that returns a
list of item dicts; the base handles HTTP, timeouts, error isolation,
and RawSignal construction.

Each subclass only needs to worry about *parsing* its specific target
page. Everything else — fetching, retries, dedup, emission, health
tracking — comes from BaseConnector.

Item dict contract (what parse_html() must return):
    [{
        "title": "Net FPI flow Apr 17: -2,340 cr",   # REQUIRED
        "url": "https://nsdl.../fpi.html#2026-04-17", # REQUIRED (include date fragment for per-day dedup)
        "body": "Equity: -1,800; Debt: -540; ...",   # optional
        "published_at": "2026-04-17T00:00:00+00:00", # optional, ISO8601
        "payload": {"equity": -1800, "debt": -540},  # optional, JSON-serialised
    }, ...]
"""
from __future__ import annotations

import abc
import json
from typing import AsyncIterator, Optional

import httpx
import structlog

from ingestion.base import BaseConnector, RawSignal

logger = structlog.get_logger()

DEFAULT_TIMEOUT = 20.0
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestAI/1.0; +https://investai.co.in/bot)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Cap per-pass items so one bad page can't flood the stream.
MAX_ITEMS_PER_PASS = 50

# Protect LLM prompt size downstream.
MAX_BODY_CHARS = 4000


class ScrapeConnector(BaseConnector):
    """Abstract HTML-scrape connector. Subclass + implement `parse_html()`."""

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
        self._http = http_client

    async def fetch(self) -> AsyncIterator[RawSignal]:
        html = await self._fetch_html()
        if not html:
            return

        try:
            items = self.parse_html(html)
        except Exception as e:
            self._log.warning("scrape.parse_failed", url=self.url, error=str(e))
            return

        for item in items[:MAX_ITEMS_PER_PASS]:
            try:
                signal = self._item_to_signal(item)
            except Exception as e:
                self._log.warning(
                    "scrape.item_failed",
                    url=self.url,
                    error=str(e),
                )
                continue

            if signal is not None:
                yield signal

    @abc.abstractmethod
    def parse_html(self, html: str) -> list[dict]:
        """Return a list of item dicts. See module docstring for contract.

        Subclasses SHOULD handle partial-parse gracefully — return whatever
        items could be parsed, log or skip the rest. Raising from here
        aborts the whole pass.
        """
        raise NotImplementedError

    async def _fetch_html(self) -> Optional[str]:
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
            self._log.warning("scrape.fetch_failed", url=self.url, error=str(e))
            return None
        finally:
            if owns_client:
                await client.aclose()

    def _item_to_signal(self, item: dict) -> Optional[RawSignal]:
        title = (item.get("title") or "").strip()
        link = (item.get("url") or "").strip()
        if not title or not link:
            return None

        body = (item.get("body") or "").strip()[:MAX_BODY_CHARS]
        published_at = item.get("published_at")

        payload = item.get("payload")
        raw_payload: Optional[str] = None
        if payload is not None:
            try:
                raw_payload = json.dumps(payload, default=str)
            except (TypeError, ValueError):
                raw_payload = None

        return RawSignal(
            source_name=self.name,
            source_region=self.region,
            source_tier=self.tier,
            category=self.category,
            url=link,
            title=title,
            body=body,
            published_at=published_at,
            raw_payload=raw_payload,
        )
