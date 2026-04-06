"""CLI entry point for the offline backtest harness.

Run from inside `backend/` so imports resolve the same way the rest of
the codebase expects:

    cd backend
    python -m evaluation.run [--lookback-years 10] [--skip-ingest] [--skip-neo4j-update]
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, timedelta

import structlog

from database.connection import AsyncSessionLocal
from evaluation.backtest import run_backtest
from evaluation.calibrate import aggregate, persist_stats, update_neo4j_edges
from evaluation.events_loader import load_events
from evaluation.price_loader import ingest_all

logger = structlog.get_logger()


async def _open_neo4j_driver():
    """Open an async Neo4j driver using the same env vars the rest of the
    backend uses. Returns None if the neo4j package is not installed or
    the driver fails to connect — the rest of the pipeline degrades to
    the hardcoded fallback KG, which is still useful for smoke tests."""
    try:
        from neo4j import AsyncGraphDatabase
    except Exception as e:
        logger.warning("run.neo4j_import_failed", error=str(e))
        return None

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j")
    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        # Smoke check
        async with driver.session() as s:
            await (await s.run("RETURN 1 AS ok")).single()
        return driver
    except Exception as e:
        logger.warning("run.neo4j_connect_failed", uri=uri, error=str(e))
        return None


async def main(
    lookback_years: int = 10,
    skip_ingest: bool = False,
    skip_neo4j_update: bool = False,
) -> None:
    end = date.today()
    start = end - timedelta(days=365 * lookback_years)

    logger.info("run.start", start=str(start), end=str(end),
                skip_ingest=skip_ingest, skip_neo4j_update=skip_neo4j_update)

    neo4j_driver = await _open_neo4j_driver()

    async with AsyncSessionLocal() as db:
        if not skip_ingest:
            stats = await ingest_all(db, start=start, end=end)
            logger.info("run.ingest_summary", symbols=len(stats), rows=sum(stats.values()))
        else:
            logger.info("run.ingest_skipped")

        events = load_events()
        logger.info("run.events_loaded", count=len(events))

        results = await run_backtest(db, neo4j_driver, events)
        edge_stats = aggregate(results)
        persisted = await persist_stats(db, edge_stats)

        if not skip_neo4j_update:
            updated = await update_neo4j_edges(neo4j_driver, edge_stats)
        else:
            updated = 0
            logger.info("run.neo4j_update_skipped")

    if neo4j_driver is not None:
        try:
            await neo4j_driver.close()
        except Exception:
            pass

    events_with_rows = len({(s.event_name, s.sector) for s in edge_stats})
    coverage = events_with_rows / len(events) if events else 0.0
    logger.info(
        "run.done",
        events_total=len(events),
        backtest_rows=len(results),
        edge_stats_rows=len(edge_stats),
        persisted_rows=persisted,
        neo4j_edges_updated=updated,
        event_sector_coverage=round(coverage, 3),
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="InvestAI backtest harness")
    p.add_argument("--lookback-years", type=int, default=10,
                   help="How many years of history to ingest (default: 10)")
    p.add_argument("--skip-ingest", action="store_true",
                   help="Skip yfinance ingestion and reuse existing sector_prices rows")
    p.add_argument("--skip-neo4j-update", action="store_true",
                   help="Skip writing measured_* props back to Neo4j CAUSES edges")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(
        lookback_years=args.lookback_years,
        skip_ingest=args.skip_ingest,
        skip_neo4j_update=args.skip_neo4j_update,
    ))
