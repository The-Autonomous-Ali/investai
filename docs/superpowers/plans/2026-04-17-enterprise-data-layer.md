# Enterprise Data Layer — Global Feed Expansion + Ingestion Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the banker's data ingestion from "India-heavy + 5 global tickers" to enterprise-grade global coverage: every major economy that affects India (US, EU, UK, Japan, China) + full commodity suite + supply chain + geopolitical. All sources must be **genuine (official or major established media) and free (no paid tier, no license fee)**. Introduce a Redis Streams queue between scraping and signal extraction so feed failures can't take down the reasoning pipeline.

**Architecture:** New `backend/ingestion/` package, one connector module per source type (RSS, REST, yfinance, scrape). Each connector pushes to a Redis Stream (`signals.raw`). A single `signal_extractor` worker consumes the stream, dedupes by `content_hash`, runs LLM extraction, and writes to the existing `signals` table with the new `source_region` and `source_tier` columns.

**Spec reference:** `docs/superpowers/specs/2026-04-16-24-7-banker-design.md` §Data Layer. Aligns with Phase 2 of the 4-phase roadmap (`project_24_7_banker_phased_plan.md`).

**Why this, why now:** The reasoning agents (`global_macro_agent.py`) already know how Fed, ECB, PBOC, commodities, and geopolitics transmit to Indian markets. They just don't have the input data. This plan closes that gap.

---

## Part 1 — The Feed Catalog (all genuine, all free)

### US (highest India impact via FII flows + dollar)
| Source | Type | URL |
|---|---|---|
| Federal Reserve press releases | RSS | `https://www.federalreserve.gov/feeds/press_monetary.xml` |
| FOMC statements | RSS | `https://www.federalreserve.gov/feeds/press_all.xml` |
| US Treasury press | RSS | `https://home.treasury.gov/rss/press-releases` |
| SEC EDGAR filings | Atom | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom` |
| BLS latest (jobs, CPI) | RSS | `https://www.bls.gov/feed/bls_latest.rss` |
| BEA (GDP, PCE) | RSS | `https://www.bea.gov/news/rss.xml` |
| FRED macroeconomic data | REST API (free key) | `https://fred.stlouisfed.org/docs/api/fred/` |
| Reuters US Markets | RSS | `https://www.reutersagency.com/feed/?best-sectors=business-finance` |
| CNBC Top News | RSS | `https://www.cnbc.com/id/100003114/device/rss/rss.html` |
| MarketWatch Top Stories | RSS | `https://feeds.marketwatch.com/marketwatch/topstories/` |

### EU + UK
| Source | Type | URL |
|---|---|---|
| ECB press releases | RSS | `https://www.ecb.europa.eu/rss/press.html` |
| Bank of England news | RSS | `https://www.bankofengland.co.uk/rss/news` |
| Eurostat news | RSS | `https://ec.europa.eu/eurostat/en/web/rss` |
| FT markets (free tier headlines) | RSS | `https://www.ft.com/markets?format=rss` |
| Reuters Europe | RSS | via Google News query |

### Japan
| Source | Type | URL |
|---|---|---|
| Bank of Japan news | RSS | `https://www.boj.or.jp/en/rss/whatsnew.xml` |
| Japan MoF | Scrape | `https://www.mof.go.jp/english/` |
| Nikkei Asia (headlines) | RSS | `https://asia.nikkei.com/rss` |

### China (critical — huge spillover to India, "China+1" thesis)
| Source | Type | URL |
|---|---|---|
| PBOC English | Scrape | `http://www.pbc.gov.cn/en/3688006/index.html` |
| CSRC (China SEC equivalent) | Scrape | `http://www.csrc.gov.cn/csrc_en/` |
| Caixin Global English | RSS | `https://www.caixinglobal.com/rss/` |
| SCMP business | RSS | `https://www.scmp.com/rss/92/feed` |
| NBS China statistics | Scrape | `http://www.stats.gov.cn/english/` |
| Shanghai Stock Exchange announcements | Scrape | `http://english.sse.com.cn/` |

### India (add to existing — current code has RBI, SEBI, ET, Mint, MC)
| Source | Type | URL |
|---|---|---|
| PIB (Press Information Bureau) | RSS | `https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3` |
| IMD (weather/monsoon) | Scrape | `https://mausam.imd.gov.in/` |
| MOSPI (statistics ministry) | RSS | `https://www.mospi.gov.in/web/mospi/rss-feed` |
| NSE corporate announcements | Scrape | `https://www.nseindia.com/corporates/content/corp_bm_announcements.htm` |
| BSE corporate announcements | Scrape | `https://www.bseindia.com/corporates/ann.html` |

### Global indices + prices (via yfinance — already integrated, expand ticker list)
| Asset class | Tickers |
|---|---|
| US indices | `^GSPC` (S&P 500), `^IXIC` (Nasdaq), `^DJI` (Dow), `^RUT` (Russell 2000), `^VIX` |
| Europe | `^GDAXI` (DAX), `^FTSE`, `^FCHI` (CAC), `^STOXX50E` |
| Asia | `^N225` (Nikkei), `^HSI` (Hang Seng), `000001.SS` (Shanghai), `^KS11` (KOSPI), `^AXJO` (ASX) |
| Bonds | `^TNX` (US 10Y, already have), `^TYX` (US 30Y), `^FVX` (US 5Y), add German Bund proxy `BUND=F` |
| FX | `EURUSD=X`, `GBPUSD=X`, `JPY=X`, `CNY=X` + `INR=X` (have) + `DXY` (have) |

### Commodities (expand from oil + gold)
| Asset | Ticker |
|---|---|
| Brent (have) | `BZ=F` |
| WTI | `CL=F` |
| Gold (have) | `GC=F` |
| Silver | `SI=F` |
| Copper | `HG=F` |
| Aluminum | `ALI=F` |
| Natural gas | `NG=F` |
| Iron ore (proxy) | `STLD` / steel ETF |
| Wheat | `ZW=F` |
| Corn | `ZC=F` |
| Sugar | `SB=F` |
| Cotton | `CT=F` |
| Crypto (risk-on gauge) | `BTC-USD`, `ETH-USD` |

### Supply chain + geopolitics
| Source | Type | URL |
|---|---|---|
| Baltic Exchange indices | Scrape | `https://www.balticexchange.com/en/data-services/market-information0.html` |
| Drewry World Container Index | Scrape | `https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry` |
| Reuters World News | RSS | via Google News query |
| BBC Business | RSS | `http://feeds.bbci.co.uk/news/business/rss.xml` |
| AP Business | RSS | `https://rsshub.app/apnews/topics/business` |
| Al Jazeera Middle East | RSS | `https://www.aljazeera.com/xml/rss/all.xml` |

### Economic calendar (for Fed meeting dates, CPI release dates, etc.)
- Investing.com economic calendar — scrape
- ForexFactory calendar — scrape
- TradingEconomics — free tier scrape

### Capital flow tracking (WHERE is the money moving — critical for rotation detection)
| Source | Type | URL | Why it matters |
|---|---|---|---|
| NSDL FPI daily flows | Scrape | `https://www.fpi.nsdl.co.in/web/Reports/Yearwise.aspx` | Official daily foreign flows into Indian equity/debt |
| BSE FII/DII activity | Scrape | `https://www.bseindia.com/markets/equity/EQReports/fii_dii_trend.aspx` | Foreign vs domestic institutional split |
| NSE FII derivatives | Scrape | `https://www.nseindia.com/market-data/fii-dii-stats` | FII positioning in futures/options |
| US TIC data | REST | `https://home.treasury.gov/data/treasury-international-capital-tic-system` | Global capital flows into/out of US |
| Credit spread proxies | yfinance | HYG/LQD ratio, EMB/TLT ratio | Risk appetite gauge |
| Key ETF flows (proxy via volume + AUM change) | yfinance | `INDA`, `INDY` (India), `FXI`, `MCHI` (China), `EWJ` (Japan), `EWZ` (Brazil), `EEM` (EM basket), `SPY`, `QQQ` | Where global money is actually going |
| India sector rotation | yfinance | All Nifty sector indices (already have) + relative strength | Detect internal rotation within India |

---

## Part 2 — Architecture Changes

### New infrastructure
- **Redis** container in `docker-compose.yml` (persistence: AOF on)
- **Redis Streams** topic: `signals.raw` (partitioned by source_region)
- **Backpressure:** MAXLEN ~= 100k, drop oldest on overflow

### New files
- `backend/ingestion/__init__.py`
- `backend/ingestion/base.py` — `BaseConnector` abstract class, common dedup + emit logic
- `backend/ingestion/connectors/rss.py` — generic RSS connector, takes feed config
- `backend/ingestion/connectors/rest.py` — generic REST (FRED, etc.)
- `backend/ingestion/connectors/yfinance_prices.py` — batched yfinance price puller
- `backend/ingestion/connectors/scrape.py` — BeautifulSoup scraper base
- `backend/ingestion/feed_registry.py` — **single source of truth** for all feeds (the catalog above in Python dict form)
- `backend/ingestion/dispatcher.py` — reads registry, schedules connectors
- `backend/services/signal_extractor.py` — consumes `signals.raw`, LLM-extracts, writes to `signals` table
- `backend/ingestion/redis_client.py` — thin async redis wrapper

### Modified files
- `backend/models/models.py` — add `source_region` (us|eu|uk|jp|cn|in|global), `source_tier` (1|2|3), `content_hash` (unique index) to `Signal`
- `backend/worker.py` — new `ingestion_dispatcher` job every 5 min; new `signal_extractor_worker` long-running consumer
- `backend/requirements.txt` — add `redis>=5.0`, `feedparser` (already there)
- `backend/scrapers/news_scraper.py` — migrate existing RSS feeds into new `feed_registry`; keep legacy shim for one release
- `backend/scrapers/market_data.py` — expand `INDIA_INDICES` and `GLOBAL_CONTEXT` per ticker table above
- `docker-compose.yml` — add `redis` service, link to `backend` and `worker`
- `backend/.env.example` — add `REDIS_URL`, `FRED_API_KEY`

### Database migration
- `backend/alembic/versions/006_signal_provenance.py` — add the three new columns to `signals` + unique index on `content_hash`

---

## Part 3 — Task Breakdown (TDD order)

### Phase A — Infrastructure (unblocks everything else)
- [ ] **A1** Add Redis to `docker-compose.yml`; verify `docker compose up redis` works
- [ ] **A2** Write `redis_client.py` + test (ping, XADD, XREADGROUP roundtrip)
- [ ] **A3** Write `base.py` `BaseConnector` + test (dedup by content_hash, emit to stream)
- [ ] **A4** Write alembic migration `006_signal_provenance.py` + test

### Phase B — Connectors (one file per type)
- [ ] **B1** Write `connectors/rss.py` generic RSS connector + tests (tier 1 + tier 2 fixtures)
- [ ] **B2** Write `connectors/rest.py` + tests (FRED fixture)
- [ ] **B3** Write `connectors/yfinance_prices.py` + tests (mock yfinance)
- [ ] **B4** Write `connectors/scrape.py` base + tests (one scrape fixture)

### Phase C — Feed registry (the catalog)
- [ ] **C1** Port existing India RSS feeds from `news_scraper.py` into `feed_registry.py`
- [ ] **C2** Add US feeds from catalog table
- [ ] **C3** Add EU + UK + Japan feeds
- [ ] **C4** Add China feeds (mix of RSS + scrape)
- [ ] **C5** Expand `market_data.py` ticker lists per Part 1

### Phase D — Consumer
- [ ] **D1** Write `signal_extractor.py` that consumes `signals.raw`, calls existing LLM extraction, writes to `signals` table + tests
- [ ] **D2** Wire `signal_extractor_worker` into `worker.py`
- [ ] **D3** Wire `ingestion_dispatcher` into `worker.py` (scheduled every 5 min)

### Phase E — Validation + cutover
- [ ] **E1** Integration test: end-to-end one signal from Fed RSS → stream → DB → `global_macro_agent` output
- [ ] **E2** Run in Codespace for 24h, inspect `signals` table for all source_regions (us, eu, uk, jp, cn, in, global)
- [ ] **E3** Retire `scrapers/news_scraper.py` legacy shim once parity confirmed

---

## Part 4 — Success Criteria

1. `signals` table, after 24h of operation, contains rows from **all 7 source_regions** (us, eu, uk, jp, cn, in, global)
2. Killing any single connector (e.g. `docker restart` just that process) does not stop other connectors from emitting
3. Restart of `backend` service does not lose in-flight signals (Redis persistence verified)
4. `global_macro_agent` output includes at least one non-India signal in its `signal_scores` array (proves data is reaching reasoning layer)
5. Zero duplicate signals (same content_hash) in the `signals` table
6. Ingestion cost = ₹0/month (Redis is self-hosted in Codespace; all feeds are free)

---

## Part 5 — Non-goals (do NOT do here)

- Paid data APIs (Bloomberg, Refinitiv, S&P Capital IQ) — violates "free" requirement
- Real-time tick data / L2 order book — not needed for a 24/7 advice product
- Social media sentiment (Twitter/Reddit) — separate effort; rate limits + auth complexity
- Writing new reasoning agents — reuse existing ones; this plan is purely about the data layer
- Replacing Postgres with a time-series DB — pgvector + partitioned tables is enough at current scale

---

## Part 6 — Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Some RSS feeds break their URL | Each connector has independent error handling; feed_registry has `health_url` for monitoring |
| LLM rate limits (Groq) with expanded signal volume | Signal extractor batches multiple raw items per LLM call; falls back to Kaggle Gemma per budget memory |
| Redis memory growth | `MAXLEN ~= 100k` on stream, 7-day retention on processed signals |
| Scraped sources change HTML | Scrape connectors are wrapped in try/except; health check surfaces failures in `/api/health` |
| SEBI audit asks source provenance | Every signal row has `source_url`, `source_tier`, `content_hash`, fetched_at — full trace |

---

## Part 7 — What ships after this plan lands

After Phase E: the banker has enterprise-grade senses. Any new feed = one-line registry entry. From this point, Phase 2 trust mechanics (source citations in output, 2+ source rule) become trivial to add because the provenance data is already there.

---

## Part 8 — Product behaviors this data unlocks

This plan is a DATA layer plan. The reasoning agents already exist. Once data reaches them:

**Cross-market rotation detection**
`global_macro_agent.py` already outputs `risk_regime`, `macro_tailwinds_for_india`, `macro_headwinds_for_india`, `affected_india_sectors`. With global price + flow data flowing in, it can now detect patterns like "US tech selling → Asian tech next → IT export tailwind for India" in real time.

**Capital flow intelligence**
FII/DII daily flows + global ETF flow proxies + credit spreads feed a new `capital_flow_agent` (to be scoped separately) that answers "where is the smart money going right now and what does that imply for India?".

**Strategy generation + update loop**
Existing `AdviceRecord` + `AdviceSignalLink` + `signal_monitor` already implement the update loop: advice is stored with the signals that supported it, and when those signals change, the monitor raises alerts. Scaling this = more signals, not more code.

**Probabilistic output (institutional-grade language)**
Every advice/strategy output MUST include:
- `probability: float` (0-1)  — e.g., 0.70 for "70% chance"
- `confidence_level`: low | medium | high  — self-assessed by the agent
- `calibration_basis`: "N past similar setups, M resolved as predicted"  — uses existing `evaluation/calibrate.py`
- `time_horizon`: explicit (e.g., "next 30 days")
- `disconfirming_conditions`: what would invalidate this thesis

This is a schema change to the LLM output contract in `agents_impl.py`, scheduled as a follow-up ticket after this data layer lands. Added here as a note so the ingestion layer can include the `historical_outcome_link` fields needed to calibrate.
