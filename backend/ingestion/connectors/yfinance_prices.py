"""yfinance-based price connector — batched global price pulls.

Pulls a snapshot of prices for a configured ticker group (e.g. "us_indices",
"commodities", "global_etf_flows"). One instance per logical group so
failures are isolated and health monitoring is granular.

yfinance is synchronous — we run it in a thread via asyncio.to_thread so
the ingestion loop doesn't block. Ticker lookups are batched in a single
yfinance call for efficiency.

Output: one RawSignal per ticker, carrying the latest close + change
as a JSON-encoded `raw_payload`. The signal_extractor consumer can then
reason about cross-asset moves (e.g. "^VIX up 15% + ^GSPC down 2%
+ GC=F up 3% → risk-off regime").
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

import structlog

from ingestion.base import BaseConnector, RawSignal

logger = structlog.get_logger()


class YFinancePricesConnector(BaseConnector):
    """One instance per ticker group.

    Example:
        us_indices = YFinancePricesConnector(
            name="yf-us-indices",
            tickers=["^GSPC", "^IXIC", "^DJI", "^VIX"],
            region="us",
            tier=1,
            category="markets",
        )
        await us_indices.run()
    """

    def __init__(
        self,
        name: str,
        tickers: list[str],
        region: str,
        tier: int,
        category: str,
    ) -> None:
        super().__init__()
        self.name = name
        self.tickers = tickers
        self.region = region
        self.tier = tier
        self.category = category

    async def fetch(self) -> AsyncIterator[RawSignal]:
        snapshots = await asyncio.to_thread(self._pull_snapshots)
        now_iso = datetime.now(timezone.utc).isoformat()

        for ticker, snap in snapshots.items():
            try:
                yield self._snapshot_to_signal(ticker, snap, now_iso)
            except Exception as e:
                self._log.warning(
                    "yfinance.signal_build_failed",
                    ticker=ticker,
                    error=str(e),
                )
                continue

    def _pull_snapshots(self) -> dict[str, dict]:
        """Synchronous batch pull. Returns {ticker: {price, change_pct, prev_close}}.

        Tickers that fail individually are skipped — a delisted ticker in
        the batch must not kill the other prices.
        """
        try:
            import yfinance as yf
        except ImportError:
            self._log.error("yfinance.not_installed")
            return {}

        out: dict[str, dict] = {}
        try:
            # yfinance download with group_by='ticker' returns a multi-index
            # DataFrame over the last 5 days (enough for prev-close compare).
            # period='5d' is cheap; interval='1d' = one row per day.
            data = yf.download(
                self.tickers,
                period="5d",
                interval="1d",
                group_by="ticker",
                progress=False,
                auto_adjust=True,
                threads=True,
            )
        except Exception as e:
            self._log.warning("yfinance.download.failed", error=str(e))
            return {}

        for ticker in self.tickers:
            try:
                # Single-ticker DataFrames don't have the outer ticker layer
                if len(self.tickers) == 1:
                    frame = data
                else:
                    frame = data[ticker]
                closes = frame["Close"].dropna()
                if len(closes) < 2:
                    continue
                prev = float(closes.iloc[-2])
                latest = float(closes.iloc[-1])
                if prev == 0:
                    continue
                change_pct = (latest - prev) / prev * 100.0
                out[ticker] = {
                    "price": latest,
                    "prev_close": prev,
                    "change_pct": change_pct,
                }
            except Exception as e:
                self._log.warning(
                    "yfinance.ticker.failed",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        return out

    def _snapshot_to_signal(
        self,
        ticker: str,
        snap: dict,
        now_iso: str,
    ) -> RawSignal:
        change = snap["change_pct"]
        direction = "↑" if change >= 0 else "↓"
        title = (
            f"{ticker}: {snap['price']:.2f} "
            f"({direction}{abs(change):.2f}% vs prior close {snap['prev_close']:.2f})"
        )
        body = (
            f"Latest close {snap['price']:.4f}. "
            f"Previous close {snap['prev_close']:.4f}. "
            f"Change {change:+.3f}%."
        )
        payload = json.dumps(
            {
                "ticker": ticker,
                "price": snap["price"],
                "prev_close": snap["prev_close"],
                "change_pct": change,
            }
        )

        # URL is synthetic so content_hash differs per (date, ticker).
        # We include the UTC date so re-runs on the same day dedup, but
        # tomorrow's run emits a fresh signal.
        today = now_iso.split("T")[0]
        url = f"yfinance://{ticker}/{today}"

        return RawSignal(
            source_name=f"{self.name}:{ticker}",
            source_region=self.region,
            source_tier=self.tier,
            category=self.category,
            url=url,
            title=title,
            body=body,
            published_at=now_iso,
            raw_payload=payload,
        )
