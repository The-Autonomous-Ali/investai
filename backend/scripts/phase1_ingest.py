"""
Phase 1 Ingestion CLI — run signal_watcher manually with scoped parameters.

Purpose:
  Bootstrap the system with real news so the /api/agents/advice endpoint
  can return a non-empty causal chain (i.e. populated RootCause nodes in
  Neo4j and credibility-scored signals in Postgres).

Usage (from backend/ directory):
  python scripts/phase1_ingest.py                  # all tiers, default limits
  python scripts/phase1_ingest.py --tier 1         # tier 1 only (8 central banks & regulators)
  python scripts/phase1_ingest.py --tier 1 --limit 5   # cap entries per feed
  python scripts/phase1_ingest.py --dry-run        # show what would be scanned, no writes

Why this exists as a script rather than a HTTP endpoint:
  - The full Phase 1 run can take 30–60 minutes on Kaggle Gemma. An HTTP
    request would time out. A CLI script runs in a shell, survives broken
    browser sessions, and produces visible log output.
  - Lets us run it offline after ingesting historical news, without
    depending on the worker scheduler.

Enterprise behaviour (non-negotiable):
  - Exit code 0 only if at least one signal was successfully committed.
  - Per-feed exceptions never abort the whole run.
  - A summary report prints at the end (counts by tier, rejection reasons,
    graph nodes written, elapsed seconds).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Allow "python scripts/phase1_ingest.py" to import from the backend package
# by putting backend/ on sys.path before the agent imports.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

import structlog

from database.connection import AsyncSessionLocal
from agents.signal_watcher import SignalWatcherAgent, RSS_SOURCES

logger = structlog.get_logger()


async def _open_neo4j_driver():
    """Return an AsyncGraphDatabase driver or None if unreachable."""
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError as e:
        logger.warning("phase1.neo4j_import_failed", error=str(e))
        return None

    url      = os.getenv("NEO4J_URL",      "bolt://localhost:7687")
    user     = os.getenv("NEO4J_USER",     "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "investai123")

    try:
        driver = AsyncGraphDatabase.driver(url, auth=(user, password))
        # Force a connection check so we fail fast rather than discovering
        # a dead Neo4j 20 minutes into ingestion.
        async with driver.session() as session:
            await session.run("RETURN 1")
        logger.info("phase1.neo4j_connected", url=url)
        return driver
    except Exception as e:
        logger.warning("phase1.neo4j_connect_failed", url=url, error=str(e))
        return None


async def _open_redis():
    try:
        import redis.asyncio as aioredis
        redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        await redis.ping()
        logger.info("phase1.redis_connected")
        return redis
    except Exception as e:
        logger.warning("phase1.redis_connect_failed", error=str(e))
        return None


async def _graph_stats(driver) -> dict:
    if driver is None:
        return {"nodes": 0, "relationships": 0, "note": "no_driver"}
    try:
        async with driver.session() as session:
            nodes_result = await session.run("MATCH (n) RETURN count(n) AS c")
            nodes_row = await nodes_result.single()
            rels_result = await session.run("MATCH ()-[r]->() RETURN count(r) AS c")
            rels_row = await rels_result.single()
            root_result = await session.run("MATCH (r:RootCause) RETURN count(r) AS c")
            root_row = await root_result.single()
            return {
                "nodes":          nodes_row["c"] if nodes_row else 0,
                "relationships":  rels_row["c"] if rels_row else 0,
                "root_causes":    root_row["c"] if root_row else 0,
            }
    except Exception as e:
        return {"error": str(e)}


def _plan_sources(tier: int | None) -> list[dict]:
    return [s for s in RSS_SOURCES if tier is None or s["tier"] == tier]


async def run(tier: int | None, limit: int, dry_run: bool) -> int:
    start_time = time.time()
    planned    = _plan_sources(tier)

    logger.info(
        "phase1.start",
        tier_filter=tier,
        max_entries_per_feed=limit,
        dry_run=dry_run,
        sources_planned=len(planned),
    )
    for src in planned:
        logger.info("phase1.source", name=src["name"], tier=src["tier"], region=src.get("region"))

    if dry_run:
        logger.info("phase1.dry_run_complete", would_scan=len(planned))
        return 0

    neo4j_driver = await _open_neo4j_driver()
    redis        = await _open_redis()
    graph_before = await _graph_stats(neo4j_driver)
    logger.info("phase1.graph_before", **graph_before)

    total_signals = 0
    try:
        async with AsyncSessionLocal() as db:
            agent = SignalWatcherAgent(db, redis, neo4j_driver=neo4j_driver)
            signals = await agent.scan_all_sources(
                tier_filter=tier,
                max_entries_per_feed=limit,
            )
            total_signals = len(signals)
    finally:
        if neo4j_driver is not None:
            try:
                await neo4j_driver.close()
            except Exception as e:
                logger.warning("phase1.neo4j_close_failed", error=str(e))
        if redis is not None:
            try:
                await redis.close()
            except Exception as e:
                logger.warning("phase1.redis_close_failed", error=str(e))

    # Re-open a short-lived driver just for the "after" count so we can see
    # how many graph nodes landed.
    after_driver = await _open_neo4j_driver()
    graph_after  = await _graph_stats(after_driver)
    if after_driver is not None:
        await after_driver.close()

    elapsed = round(time.time() - start_time, 1)
    logger.info(
        "phase1.complete",
        signals_saved=total_signals,
        elapsed_seconds=elapsed,
        graph_before=graph_before,
        graph_after=graph_after,
    )

    # Exit code contract: 0 = success (>=1 signal saved), 1 = zero signals
    # (which could still mean "no new news" but the operator should notice).
    return 0 if total_signals > 0 else 1


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 1 ingestion — scoped RSS scan")
    p.add_argument("--tier", type=int, choices=[1, 2, 3], default=None,
                   help="Only scan sources in this tier. Omit for all tiers.")
    p.add_argument("--limit", type=int, default=10,
                   help="Max entries classified per RSS feed (default 10)")
    p.add_argument("--dry-run", action="store_true",
                   help="List sources that would be scanned and exit without touching the DBs")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    code = asyncio.run(run(tier=args.tier, limit=args.limit, dry_run=args.dry_run))
    sys.exit(code)
