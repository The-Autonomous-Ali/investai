"""FRED (Federal Reserve Economic Data) connector.

FRED is the canonical source for US macroeconomic series: Fed funds rate,
CPI, unemployment, 10Y yield, dollar index, etc. Free API, requires a
single API key (signup is instant and free at https://fred.stlouisfed.org).

One instance per series. `fetch()` yields at most one RawSignal per pass —
the latest observation. Historical backfill is out of scope here; the
reasoning agents care about CURRENT state + change vs prior reading.

If `FRED_API_KEY` env var is missing, the connector logs once and fetches
nothing — it does NOT crash the ingestion dispatcher. This matches the
"fail soft per connector" principle from the plan.

API docs: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import httpx
import structlog

from ingestion.base import BaseConnector, RawSignal

logger = structlog.get_logger()

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_TIMEOUT = 15.0


class FredSeriesConnector(BaseConnector):
    """One FRED series per instance.

    Example:
        fed_funds = FredSeriesConnector(
            name="fred-fed-funds",
            series_id="DFF",
            human_label="US Fed Funds Rate",
            region="us",
            tier=1,
            category="monetary",
        )
        await fed_funds.run()
    """

    def __init__(
        self,
        name: str,
        series_id: str,
        human_label: str,
        region: str,
        tier: int,
        category: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.series_id = series_id
        self.human_label = human_label
        self.region = region
        self.tier = tier
        self.category = category
        self._http = http_client

    async def fetch(self) -> AsyncIterator[RawSignal]:
        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            self._log.warning("fred.no_api_key", series_id=self.series_id)
            return

        observations = await self._fetch_observations(api_key)
        if not observations:
            return

        # Latest two observations: for the change-vs-prior rendering.
        # FRED returns oldest-first when sort_order is asc (default);
        # we requested desc so observations[0] is latest.
        latest = observations[0]
        prior = observations[1] if len(observations) > 1 else None

        try:
            signal = self._build_signal(latest, prior)
        except Exception as e:
            self._log.warning(
                "fred.signal_build_failed",
                series_id=self.series_id,
                error=str(e),
            )
            return

        if signal is not None:
            yield signal

    async def _fetch_observations(self, api_key: str) -> list[dict]:
        params = {
            "series_id": self.series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2,
        }

        owns_client = self._http is None
        client = self._http or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        try:
            resp = await client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("observations", [])
        except Exception as e:
            self._log.warning(
                "fred.fetch.failed",
                series_id=self.series_id,
                error=str(e),
            )
            return []
        finally:
            if owns_client:
                await client.aclose()

    def _build_signal(
        self,
        latest: dict,
        prior: Optional[dict],
    ) -> Optional[RawSignal]:
        # FRED marks missing values as "." — skip those.
        latest_val = self._to_float(latest.get("value"))
        if latest_val is None:
            return None

        latest_date = latest.get("date", "")
        prior_val = self._to_float(prior.get("value")) if prior else None

        change_pct: Optional[float] = None
        if prior_val is not None and prior_val != 0:
            change_pct = (latest_val - prior_val) / abs(prior_val) * 100.0

        # Title: "US Fed Funds Rate: 4.33 (-0.25pp vs 2026-03)"
        if change_pct is not None and prior:
            direction = "↑" if change_pct >= 0 else "↓"
            title = (
                f"{self.human_label}: {latest_val:g} "
                f"({direction}{abs(change_pct):.2f}% vs {prior.get('date', 'prior')})"
            )
        else:
            title = f"{self.human_label}: {latest_val:g}"

        body = (
            f"FRED series {self.series_id} latest observation "
            f"{latest_val:g} on {latest_date}."
        )
        if prior_val is not None:
            body += f" Prior: {prior_val:g} on {prior.get('date', '')}."

        payload = json.dumps(
            {
                "series_id": self.series_id,
                "latest_value": latest_val,
                "latest_date": latest_date,
                "prior_value": prior_val,
                "prior_date": prior.get("date") if prior else None,
                "change_pct": change_pct,
            }
        )

        url = f"https://fred.stlouisfed.org/series/{self.series_id}"
        published_at = self._date_to_iso(latest_date)

        return RawSignal(
            source_name=self.name,
            source_region=self.region,
            source_tier=self.tier,
            category=self.category,
            url=f"{url}#obs-{latest_date}",  # makes content_hash unique per observation
            title=title,
            body=body,
            published_at=published_at,
            raw_payload=payload,
        )

    @staticmethod
    def _to_float(v) -> Optional[float]:
        if v is None:
            return None
        s = str(v).strip()
        if s in ("", "."):
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _date_to_iso(date_str: str) -> Optional[str]:
        if not date_str:
            return None
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
