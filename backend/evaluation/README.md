# Backtest Harness — `backend/evaluation/`

Offline ground-truth loop for the global→local signal chain. This package
does **not** run in the live request path. It exists so that every
`(:Event)-[:CAUSES]->(:Sector)` edge in the knowledge graph has a
measured hit rate and alpha, derived from real historical Indian sector
returns instead of hand-seeded constants.

## What it does

1. **Ingests 10 years of daily closes** for 10 Indian sector indices +
   5 global context tickers into the `sector_prices` table via yfinance.
2. **Loads a seeded catalog** of ~40 historical global→India events from
   `historical_events.yaml`.
3. **Replays each event through the KG**: for every event, queries Neo4j
   for the affected sectors and their predicted direction.
4. **Measures actual sector alpha** vs. the Nifty 50 benchmark at lag
   windows of 5, 20, and 60 trading days.
5. **Aggregates** results into per-edge statistics (hit rate, avg alpha,
   Wilson 95% CI) and upserts them into `kg_edge_stats`.
6. **Writes the primary-lag summary back onto Neo4j** `CAUSES` edges as
   `measured_strength`, `measured_hit_rate`, `measured_sample_size`,
   `last_calibrated_at`.

## How to run it

From inside the `backend/` directory, with Postgres and Neo4j up via
`docker-compose`:

```bash
# 1. Apply the migration (creates sector_prices and kg_edge_stats)
alembic upgrade head

# 2. Seed the Neo4j knowledge graph if not already done
python seed_knowledge_graph.py

# 3. Run the harness
python -m evaluation.run --lookback-years 10
```

Subsequent runs are idempotent. If you only want to re-score without
re-downloading prices:

```bash
python -m evaluation.run --skip-ingest
```

To skip the Neo4j writeback (e.g. for CI):

```bash
python -m evaluation.run --skip-neo4j-update
```

## How to read the output

After a successful run, query Postgres:

```sql
SELECT event_name, sector, lag_days, sample_size, hit_rate,
       avg_alpha, measured_strength
FROM   kg_edge_stats
WHERE  lag_days = 20
ORDER  BY sample_size DESC, hit_rate DESC;
```

Example interpretation:
```
event_name       | sector  | lag_days | n | hit_rate | avg_alpha | measured_strength
-----------------+---------+----------+---+----------+-----------+------------------
Oil Price Spike  | Oil&Gas |       20 | 4 |   0.7500 |   0.0213  |           0.7500
RBI Rate Hike    | Realty  |       20 | 3 |   0.6667 |  -0.0147  |           0.6667
US Fed Rate Hike | IT      |       20 | 5 |   0.4000 |  -0.0034  |           0.0000
```

- `sample_size` is how many historical events matched this edge in the
  catalog. Treat anything below ~4 as weak evidence.
- `measured_strength` is `hit_rate` if the observed alpha sign agrees
  with the KG's predicted direction, otherwise `0.0`. It is the value
  we write back onto the Neo4j edge.
- `avg_alpha` is the sector return minus the Nifty 50 return over the
  lag window. Positive means the sector beat the benchmark.

## Unit tests

```bash
pytest tests/test_backtest.py tests/test_calibrate.py tests/test_events_loader.py -v
```

Tests use synthetic pandas Series fixtures — no Neo4j, no yfinance, no
database required.

## Known limitations (read before drawing conclusions)

- **Small samples.** Most `(event_name, sector, lag)` tuples will have
  n=2–5 over a 10-year window. Wilson CIs on n=2 are wide. Honest, but
  use the `sample_size` column to filter downstream.
- **Survivorship / reconstitution bias.** Nifty sector indices rebalance.
  The harness only claims "did the Nifty IT index move in the predicted
  direction," not attribution to specific stocks.
- **Benchmark correlation.** Nifty Bank is ~35% of Nifty 50, so
  bank-vs-Nifty alpha is structurally weak. A follow-up PR will switch
  to sector-excluded benchmarks.
- **Sector coverage.** The following Neo4j sectors have no liquid index
  proxy and are skipped: Aviation, Paints, Tyres, Infrastructure,
  Renewable Energy, Defence, Gold. These are left to a follow-up PR.
- **Date convention.** Every event date in the YAML is the first public
  trading day, not the incident timestamp. `_next_trading_day` prevents
  look-ahead on weekend or after-hours events.

## Files

| File | Purpose |
|---|---|
| `price_loader.py` | yfinance ingestion into `sector_prices`, with ticker → Neo4j-sector mapping |
| `events_loader.py` | Strict YAML schema validation → `HistoricalEvent` dataclasses |
| `historical_events.yaml` | Seeded catalog of historical global→India events |
| `kg_query.py` | Neo4j traversal tuned for the backtest, normalizes edge directions |
| `backtest.py` | Main replay loop — pure-function alpha math against pandas Series |
| `calibrate.py` | Aggregation + Wilson CI + Postgres upsert + Neo4j writeback |
| `run.py` | CLI entry point (`python -m evaluation.run`) |
