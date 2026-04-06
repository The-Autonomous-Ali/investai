"""Aggregate BacktestResult rows into per-edge statistics, persist to
`kg_edge_stats` in Postgres, and optionally write a primary-lag summary
back onto the Neo4j CAUSES edges.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev
from typing import Iterable, Sequence

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation.backtest import BacktestResult
from models.models import KGEdgeStats

logger = structlog.get_logger()

MIN_SAMPLE_SIZE: int = 2
PRIMARY_LAG_DAYS: int = 20   # the lag we write back onto the Neo4j edge


@dataclass(frozen=True)
class EdgeStats:
    event_type: str
    event_name: str
    sector: str
    lag_days: int
    sample_size: int
    hits: int
    hit_rate: float
    avg_alpha: float
    alpha_stddev: float
    ci95_low: float
    ci95_high: float
    measured_strength: float
    predicted_direction: str


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion — no scipy needed.
    Returns (lower, upper) bounds clamped to [0, 1]."""
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1.0 + (z * z) / n
    centre = (p + (z * z) / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _sign_agrees(avg_alpha: float, predicted_direction: str) -> bool:
    if avg_alpha > 0 and predicted_direction == "positive":
        return True
    if avg_alpha < 0 and predicted_direction == "negative":
        return True
    return False


def aggregate(results: Iterable[BacktestResult]) -> list[EdgeStats]:
    """Group by (signal_type, event_name, sector, lag_days) and compute
    per-group stats. Tuples with `sample_size < MIN_SAMPLE_SIZE` are
    dropped — we don't pollute persistence with n=1 noise."""
    groups: dict[tuple[str, str, str, int], list[BacktestResult]] = defaultdict(list)
    for r in results:
        groups[(r.signal_type, r.event_name, r.sector, r.lag_days)].append(r)

    out: list[EdgeStats] = []
    for (stype, ename, sector, lag), rows in groups.items():
        n = len(rows)
        if n < MIN_SAMPLE_SIZE:
            continue
        hits = sum(1 for r in rows if r.hit)
        hit_rate = hits / n
        alphas = [r.sector_alpha for r in rows]
        avg = mean(alphas)
        sd = pstdev(alphas) if n > 1 else 0.0
        lo, hi = wilson_ci(hits, n)
        pred_dir = rows[0].predicted_direction
        measured_strength = hit_rate if _sign_agrees(avg, pred_dir) else 0.0

        out.append(EdgeStats(
            event_type=stype,
            event_name=ename,
            sector=sector,
            lag_days=lag,
            sample_size=n,
            hits=hits,
            hit_rate=hit_rate,
            avg_alpha=avg,
            alpha_stddev=sd,
            ci95_low=lo,
            ci95_high=hi,
            measured_strength=measured_strength,
            predicted_direction=pred_dir,
        ))
    return out


async def persist_stats(db: AsyncSession, stats: Sequence[EdgeStats]) -> int:
    """Upsert every EdgeStats row into `kg_edge_stats` by
    (event_name, sector, lag_days)."""
    if not stats:
        return 0

    rows = [
        {
            "event_type":          s.event_type,
            "event_name":          s.event_name,
            "sector":              s.sector,
            "lag_days":            s.lag_days,
            "sample_size":         s.sample_size,
            "hits":                s.hits,
            "hit_rate":            s.hit_rate,
            "avg_alpha":           s.avg_alpha,
            "alpha_stddev":        s.alpha_stddev,
            "ci95_low":            s.ci95_low,
            "ci95_high":           s.ci95_high,
            "measured_strength":   s.measured_strength,
            "predicted_direction": s.predicted_direction,
            "calibrated_at":       datetime.utcnow(),
        }
        for s in stats
    ]

    stmt = pg_insert(KGEdgeStats.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["event_name", "sector", "lag_days"],
        set_={
            "event_type":          stmt.excluded.event_type,
            "sample_size":         stmt.excluded.sample_size,
            "hits":                stmt.excluded.hits,
            "hit_rate":            stmt.excluded.hit_rate,
            "avg_alpha":           stmt.excluded.avg_alpha,
            "alpha_stddev":        stmt.excluded.alpha_stddev,
            "ci95_low":            stmt.excluded.ci95_low,
            "ci95_high":           stmt.excluded.ci95_high,
            "measured_strength":   stmt.excluded.measured_strength,
            "predicted_direction": stmt.excluded.predicted_direction,
            "calibrated_at":       stmt.excluded.calibrated_at,
        },
    )
    await db.execute(stmt)
    await db.commit()
    logger.info("calibrate.persisted", rows=len(rows))
    return len(rows)


async def update_neo4j_edges(
    neo4j_driver,
    stats: Sequence[EdgeStats],
    primary_lag: int = PRIMARY_LAG_DAYS,
) -> int:
    """Write `measured_strength` / `measured_hit_rate` / `measured_sample_size`
    / `last_calibrated_at` onto the matching Neo4j CAUSES edge, using only
    the primary lag window. Other lag windows remain in Postgres only.
    """
    if not neo4j_driver:
        logger.warning("calibrate.neo4j_skipped", reason="no driver")
        return 0

    primary = [s for s in stats if s.lag_days == primary_lag]
    if not primary:
        logger.warning("calibrate.neo4j_skipped", reason="no stats at primary lag", lag=primary_lag)
        return 0

    query = """
    MATCH (e:Event {name: $event_name})-[r:CAUSES*1..3]->(s:Sector {name: $sector, country: 'India'})
    WITH [rel IN r WHERE type(rel) = 'CAUSES'][-1] AS final_rel
    SET final_rel.measured_strength    = $measured_strength,
        final_rel.measured_hit_rate    = $hit_rate,
        final_rel.measured_sample_size = $sample_size,
        final_rel.last_calibrated_at   = $calibrated_at
    RETURN count(final_rel) AS updated
    """
    updated = 0
    try:
        async with neo4j_driver.session() as session:
            for s in primary:
                result = await session.run(
                    query,
                    event_name=s.event_name,
                    sector=s.sector,
                    measured_strength=s.measured_strength,
                    hit_rate=s.hit_rate,
                    sample_size=s.sample_size,
                    calibrated_at=datetime.utcnow().isoformat(),
                )
                row = await result.single()
                if row and row.get("updated"):
                    updated += int(row["updated"])
    except Exception as e:
        logger.warning("calibrate.neo4j_error", error=str(e))
        return updated

    logger.info("calibrate.neo4j_updated", edges=updated)
    return updated
