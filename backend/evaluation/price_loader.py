"""Bulk historical price ingestion via yfinance.

Populates the `sector_prices` table with daily adjusted closes for the 10
Indian sector indices the backtest cares about plus a handful of global
context tickers. Idempotent: safe to re-run — existing (symbol, date) rows
are upserted so only genuinely new trading days are written.

Not to be confused with backend/scrapers/market_data.py, which is the live
request-path snapshot scraper using yfinance `fast_info`. This module is
offline and pulls multi-year history.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd
import structlog
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import SectorPrice

logger = structlog.get_logger()


# ── Ticker mapping ────────────────────────────────────────────────────────────
# Keys are the canonical `symbol` values we store in sector_prices;
# values are yfinance tickers.

SECTOR_TICKERS: dict[str, str] = {
    "NIFTY_50":       "^NSEI",
    "NIFTY_BANK":     "^NSEBANK",
    "NIFTY_IT":       "^CNXIT",
    "NIFTY_PHARMA":   "^CNXPHARMA",
    "NIFTY_AUTO":     "^CNXAUTO",
    "NIFTY_FMCG":     "^CNXFMCG",
    "NIFTY_METAL":    "^CNXMETAL",
    "NIFTY_REALTY":   "^CNXREALTY",
    "NIFTY_ENERGY":   "^CNXENERGY",
    "NIFTY_PSU_BANK": "^CNXPSUBANK",
}

GLOBAL_TICKERS: dict[str, str] = {
    "BRENT":  "BZ=F",
    "GOLD":   "GC=F",
    "DXY":    "DX-Y.NYB",
    "US10Y":  "^TNX",
    "USDINR": "INR=X",
}

ALL_TICKERS: dict[str, str] = {**SECTOR_TICKERS, **GLOBAL_TICKERS}

# Neo4j Sector.name → canonical symbol key. Sectors without an entry are
# not backtested (no liquid index proxy). Keep keys exactly matching the
# Neo4j seed in infra/neo4j/seed.cypher.
SECTOR_TO_TICKER: dict[str, str] = {
    "Banking":     "NIFTY_BANK",
    "IT":          "NIFTY_IT",
    "Pharma":      "NIFTY_PHARMA",
    "Auto":        "NIFTY_AUTO",
    "FMCG":        "NIFTY_FMCG",
    "Metals":      "NIFTY_METAL",
    "Real Estate": "NIFTY_REALTY",
    "Oil & Gas":   "NIFTY_ENERGY",
    "NBFC":        "NIFTY_PSU_BANK",   # closest liquid proxy; documented in README
}


def _compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Add returns_1d / returns_5d / returns_30d columns. Operates on a
    DataFrame with a `close` column sorted by date ascending."""
    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"].astype(float)
    df["returns_1d"]  = close.pct_change(1)
    df["returns_5d"]  = close.pct_change(5)
    df["returns_30d"] = close.pct_change(30)
    return df


def fetch_history(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch adjusted daily closes for `ticker` in [start, end). Returns a
    DataFrame with columns [date, close]. Empty DataFrame on failure."""
    try:
        raw = yf.download(
            ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning("price_loader.fetch_failed", ticker=ticker, error=str(e))
        return pd.DataFrame(columns=["date", "close"])

    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "close"])

    # yfinance returns MultiIndex columns when only one ticker is passed in
    # some versions; normalize to flat.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]

    if "Close" not in raw.columns:
        return pd.DataFrame(columns=["date", "close"])

    out = pd.DataFrame({
        "date": [d.date() if hasattr(d, "date") else d for d in raw.index],
        "close": raw["Close"].astype(float).values,
    })
    out = out.dropna(subset=["close"])
    return out


async def ingest_all(
    db: AsyncSession,
    start: date,
    end: date,
    batch_size: int = 500,
    tickers: dict[str, str] | None = None,
    sleep_between: float = 0.2,
) -> dict[str, int]:
    """Fetch every configured ticker between `start` and `end` and upsert
    into `sector_prices`. Returns a dict mapping symbol → rows written.

    Per-ticker failures are logged and do not abort the run. Postgres
    upsert on (symbol, date) makes this idempotent; re-running only writes
    genuinely new trading days.
    """
    tickers = tickers or ALL_TICKERS
    stats: dict[str, int] = {}

    for symbol, yf_ticker in tickers.items():
        log = logger.bind(symbol=symbol, yf_ticker=yf_ticker)
        df = fetch_history(yf_ticker, start, end)
        if df.empty:
            log.warning("price_loader.empty_history")
            stats[symbol] = 0
            continue

        df = _compute_returns(df)
        rows = [
            {
                "symbol":      symbol,
                "date":        r.date,
                "close":       float(r.close),
                "returns_1d":  None if pd.isna(r.returns_1d)  else float(r.returns_1d),
                "returns_5d":  None if pd.isna(r.returns_5d)  else float(r.returns_5d),
                "returns_30d": None if pd.isna(r.returns_30d) else float(r.returns_30d),
            }
            for r in df.itertuples(index=False)
        ]

        written = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            stmt = pg_insert(SectorPrice.__table__).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "date"],
                set_={
                    "close":       stmt.excluded.close,
                    "returns_1d":  stmt.excluded.returns_1d,
                    "returns_5d":  stmt.excluded.returns_5d,
                    "returns_30d": stmt.excluded.returns_30d,
                    "ingested_at": datetime.utcnow(),
                },
            )
            await db.execute(stmt)
            written += len(chunk)
        await db.commit()

        first_date = df["date"].min()
        last_date = df["date"].max()
        log.info(
            "price_loader.ingested",
            rows=written,
            first_date=str(first_date),
            last_date=str(last_date),
        )
        stats[symbol] = written

        if sleep_between:
            await asyncio.sleep(sleep_between)

    return stats


async def load_prices_from_db(
    db: AsyncSession,
    symbols: Iterable[str] | None = None,
) -> dict[str, pd.Series]:
    """Load all sector_prices rows into an in-memory dict of pd.Series
    keyed by symbol, indexed by date, ascending. Used by backtest.py so
    the main replay loop makes no DB calls."""
    q = select(SectorPrice.symbol, SectorPrice.date, SectorPrice.close)
    if symbols:
        q = q.where(SectorPrice.symbol.in_(list(symbols)))
    result = await db.execute(q)

    bucket: dict[str, list[tuple[date, float]]] = {}
    for sym, d, c in result.all():
        bucket.setdefault(sym, []).append((d, float(c)))

    out: dict[str, pd.Series] = {}
    for sym, rows in bucket.items():
        rows.sort(key=lambda x: x[0])
        idx = pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows])
        out[sym] = pd.Series([r[1] for r in rows], index=idx, name=sym)
    return out
