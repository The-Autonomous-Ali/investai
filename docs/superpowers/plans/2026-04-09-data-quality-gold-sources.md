# Data Quality + Gold Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add gold-tier data sources (FRED, BSE, RBI structured, Google News), build a credibility scoring engine that filters garbage from gold, and wire disconnected data pipes (NSE FII/DII scraper + free_data_feeds) into the live pipeline.

**Architecture:** Three new modules — `gold_data_feeds.py` (structured data fetchers), `credibility_engine.py` (scoring + filtering), and modifications to `signal_watcher.py` (Google News RSS + credibility integration). New DB columns on Signal model for credibility metadata. Worker gets new scheduled jobs for structured data fetching.

**Tech Stack:** Python, httpx, feedparser, SQLAlchemy (async), Alembic, APScheduler, existing Groq/Llama LLM via `call_llm()`

---

## Silver Source Picks

| Source | Why |
|---|---|
| **Google News RSS** | Free, no key. Used for **corroboration only** — if Reuters says X and Google News shows 5 other outlets saying X, confidence goes up. Not trusted on its own. |
| **Moneycontrol** | Already in RSS feeds. Kept as-is — will get filtered by credibility engine (tier 2 = score 0.75) |
| **Economic Times** | Already in RSS feeds. Kept as-is — same tier 2 filtering |

---

## File Structure

| Action | File | Purpose |
|--------|------|---------|
| **Create** | `backend/agents/gold_data_feeds.py` | FRED API client + BSE announcements fetcher + RBI structured data |
| **Create** | `backend/agents/credibility_engine.py` | Source scoring + claim type classification + corroboration check |
| **Create** | `backend/alembic/versions/005_credibility_scoring.py` | Migration: add credibility columns to signals table |
| **Create** | `backend/tests/test_credibility_engine.py` | Unit tests for credibility scoring |
| **Create** | `backend/tests/test_gold_data_feeds.py` | Unit tests for gold data fetchers |
| **Modify** | `backend/agents/signal_watcher.py` | Add Google News RSS, integrate credibility scoring, add corroboration check |
| **Modify** | `backend/models/models.py` | Add credibility_score, claim_type, source_urls columns to Signal |
| **Modify** | `backend/worker.py` | Add gold data fetch jobs, wire NSE FII/DII into periodic scan |

---

### Task 1: Add Credibility Columns to Signal Model

**Files:**
- Modify: `backend/models/models.py:140-180` (Signal class)
- Create: `backend/alembic/versions/005_credibility_scoring.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_credibility_columns.py`:

```python
"""Test that Signal model has credibility columns."""
import pytest
from models.models import Signal


def test_signal_has_credibility_score():
    s = Signal(title="Test", credibility_score=0.85)
    assert s.credibility_score == 0.85


def test_signal_has_claim_type():
    s = Signal(title="Test", claim_type="factual")
    assert s.claim_type == "factual"


def test_signal_has_source_urls():
    s = Signal(title="Test", source_urls=["https://reuters.com/article1"])
    assert s.source_urls == ["https://reuters.com/article1"]


def test_signal_has_corroboration_count():
    s = Signal(title="Test", corroboration_count=3)
    assert s.corroboration_count == 3


def test_signal_credibility_defaults():
    s = Signal(title="Test")
    assert s.credibility_score is None
    assert s.claim_type is None
    assert s.corroboration_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_credibility_columns.py -v`
Expected: FAIL — `Signal` has no attribute `credibility_score`

- [ ] **Step 3: Add columns to Signal model**

In `backend/models/models.py`, add these columns to the `Signal` class after `corroboration_boost`:

```python
    # Credibility scoring
    credibility_score   = Column(Float)               # 0.0-1.0 final credibility
    claim_type          = Column(String)               # factual, analysis, opinion, tip
    source_urls         = Column(JSON, default=list)   # URLs backing this signal
    corroboration_count = Column(Integer, default=0)   # number of sources reporting same event
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_credibility_columns.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Create Alembic migration**

Create `backend/alembic/versions/005_credibility_scoring.py`:

```python
"""Add credibility scoring columns to signals table.

Revision ID: 005
Revises: 003
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signals', sa.Column('credibility_score', sa.Float(), nullable=True))
    op.add_column('signals', sa.Column('claim_type', sa.String(), nullable=True))
    op.add_column('signals', sa.Column('source_urls', sa.JSON(), nullable=True))
    op.add_column('signals', sa.Column('corroboration_count', sa.Integer(), server_default='0'))


def downgrade() -> None:
    op.drop_column('signals', 'corroboration_count')
    op.drop_column('signals', 'source_urls')
    op.drop_column('signals', 'claim_type')
    op.drop_column('signals', 'credibility_score')
```

- [ ] **Step 6: Commit**

```bash
git add backend/models/models.py backend/alembic/versions/005_credibility_scoring.py backend/tests/test_credibility_columns.py
git commit -m "feat: add credibility scoring columns to Signal model"
```

---

### Task 2: Build Credibility Scoring Engine

**Files:**
- Create: `backend/agents/credibility_engine.py`
- Create: `backend/tests/test_credibility_engine.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_credibility_engine.py`:

```python
"""Tests for the credibility scoring engine."""
import pytest
from agents.credibility_engine import CredibilityEngine


@pytest.fixture
def engine():
    return CredibilityEngine()


# ── Source Score Tests ────────────────────────────────────────────────────────

def test_source_score_tier1_rbi(engine):
    score = engine.get_source_score("RBI", tier=1)
    assert score == 0.95


def test_source_score_tier2_reuters(engine):
    score = engine.get_source_score("Reuters Business", tier=2)
    assert score == 0.85


def test_source_score_tier3(engine):
    score = engine.get_source_score("OilPrice.com", tier=3)
    assert score == 0.60


def test_source_score_unknown(engine):
    score = engine.get_source_score("RandomBlog", tier=4)
    assert score == 0.30


def test_source_score_google_news(engine):
    score = engine.get_source_score("Google News", tier=3)
    assert score == 0.40


# ── Claim Type Weight Tests ──────────────────────────────────────────────────

def test_claim_weight_factual(engine):
    assert engine.get_claim_weight("factual") == 1.0


def test_claim_weight_analysis(engine):
    assert engine.get_claim_weight("analysis") == 0.7


def test_claim_weight_opinion(engine):
    assert engine.get_claim_weight("opinion") == 0.4


def test_claim_weight_tip_rejected(engine):
    assert engine.get_claim_weight("tip") == 0.0


def test_claim_weight_unknown_defaults_to_analysis(engine):
    assert engine.get_claim_weight("unknown") == 0.7


# ── Corroboration Multiplier Tests ───────────────────────────────────────────

def test_corroboration_3_plus_sources(engine):
    assert engine.get_corroboration_multiplier(3) == 1.3


def test_corroboration_2_sources(engine):
    assert engine.get_corroboration_multiplier(2) == 1.1


def test_corroboration_single_source(engine):
    assert engine.get_corroboration_multiplier(1) == 0.8


def test_corroboration_zero_sources(engine):
    assert engine.get_corroboration_multiplier(0) == 0.8


# ── Final Score Tests ────────────────────────────────────────────────────────

def test_final_score_gold_factual_corroborated(engine):
    """RBI factual news corroborated by 3 sources = highest credibility."""
    score = engine.compute_credibility(
        source_name="RBI", tier=1, claim_type="factual", corroboration_count=3
    )
    # 0.95 * 1.0 * 1.3 = 1.235 → capped at 1.0
    assert score == 1.0


def test_final_score_silver_opinion_single(engine):
    """Moneycontrol opinion, single source = low credibility."""
    score = engine.compute_credibility(
        source_name="Moneycontrol", tier=2, claim_type="opinion", corroboration_count=1
    )
    # 0.85 * 0.4 * 0.8 = 0.272
    assert round(score, 2) == 0.27


def test_final_score_tip_always_zero(engine):
    """Tips are always rejected regardless of source."""
    score = engine.compute_credibility(
        source_name="RBI", tier=1, claim_type="tip", corroboration_count=5
    )
    assert score == 0.0


def test_final_score_threshold(engine):
    """Signals below 0.5 should be flagged as low credibility."""
    score = engine.compute_credibility(
        source_name="RandomBlog", tier=4, claim_type="opinion", corroboration_count=1
    )
    assert score < 0.5
    assert engine.passes_threshold(score) is False


def test_passes_threshold(engine):
    assert engine.passes_threshold(0.6) is True
    assert engine.passes_threshold(0.5) is True
    assert engine.passes_threshold(0.49) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_credibility_engine.py -v`
Expected: FAIL — `No module named 'agents.credibility_engine'`

- [ ] **Step 3: Implement the credibility engine**

Create `backend/agents/credibility_engine.py`:

```python
"""
Credibility Scoring Engine — Separates garbage from gold.

Every signal gets scored on three axes:
1. SOURCE_SCORE — How trustworthy is the source? (hardcoded lookup)
2. CLAIM_WEIGHT — Is this fact, analysis, opinion, or a tip? (LLM classifies)
3. CORROBORATION — How many independent sources report the same thing?

Final credibility = min(source_score * claim_weight * corroboration_multiplier, 1.0)
Threshold: Only signals with credibility >= 0.5 enter the pipeline.
"""
import structlog
from difflib import SequenceMatcher

logger = structlog.get_logger()

# ── Source Credibility Scores ────────────────────────────────────────────────
# Based on editorial standards, regulatory status, fact-checking history

SOURCE_SCORES = {
    # Tier 1: Government/Regulatory — publish verified data, not opinions
    "US Federal Reserve":     0.95,
    "European Central Bank":  0.95,
    "RBI":                    0.95,
    "SEBI":                   0.95,
    "Ministry of Finance":    0.95,
    "IMF":                    0.95,
    "World Bank":             0.95,
    "OPEC":                   0.95,
    "FRED":                   0.95,
    "BSE Announcements":      0.95,
    "RBI Data":               0.95,
    "PIB":                    0.95,
    "NSE FII/DII":            0.95,

    # Tier 2: Major wire services + established financial media
    "Reuters Business":       0.85,
    "Reuters Top News":       0.85,
    "BBC Business":           0.85,
    "NYT Business":           0.85,
    "Wall Street Journal":    0.85,
    "Economic Times Markets": 0.75,
    "Economic Times Economy": 0.75,
    "Mint Markets":           0.75,
    "Mint Economy":           0.75,
    "Business Standard":      0.75,
    "Moneycontrol":           0.75,
    "Financial Express":      0.75,

    # Tier 3: Specialized/regional — useful but narrower editorial control
    "OilPrice.com":           0.60,
    "Mining.com":             0.60,
    "SCMP China Business":    0.60,
    "Japan News":             0.60,
    "Arabian Business":       0.60,
    "Hindu BusinessLine":     0.65,

    # Silver: Aggregators — good for corroboration, not for primary trust
    "Google News":            0.40,
}

# Fallback scores by tier when source name not in lookup
TIER_FALLBACK_SCORES = {
    1: 0.95,
    2: 0.75,
    3: 0.60,
    4: 0.30,
}

# ── Claim Type Weights ───────────────────────────────────────────────────────

CLAIM_WEIGHTS = {
    "factual":  1.0,    # "RBI raised rates by 25bps" — verifiable fact
    "analysis": 0.7,    # "Markets may fall due to..." — informed reasoning
    "opinion":  0.4,    # "I think Reliance will..." — subjective view
    "tip":      0.0,    # "Buy X at Y price" — REJECTED entirely
}

CREDIBILITY_THRESHOLD = 0.5


class CredibilityEngine:
    """Scores every signal for trustworthiness before it enters the pipeline."""

    def get_source_score(self, source_name: str, tier: int = 3) -> float:
        """Lookup source credibility score. Falls back to tier-based score."""
        if source_name in SOURCE_SCORES:
            return SOURCE_SCORES[source_name]
        return TIER_FALLBACK_SCORES.get(tier, 0.30)

    def get_claim_weight(self, claim_type: str) -> float:
        """Get weight for a claim type. Unknown defaults to 'analysis'."""
        return CLAIM_WEIGHTS.get(claim_type, CLAIM_WEIGHTS["analysis"])

    def get_corroboration_multiplier(self, corroboration_count: int) -> float:
        """Score boost/penalty based on how many sources report the same event."""
        if corroboration_count >= 3:
            return 1.3
        elif corroboration_count == 2:
            return 1.1
        else:
            return 0.8  # single source = penalty

    def compute_credibility(
        self,
        source_name: str,
        tier: int,
        claim_type: str,
        corroboration_count: int = 1,
    ) -> float:
        """Compute final credibility score for a signal.

        Returns 0.0-1.0 (capped). Tips always return 0.0.
        """
        source_score = self.get_source_score(source_name, tier)
        claim_weight = self.get_claim_weight(claim_type)
        corroboration = self.get_corroboration_multiplier(corroboration_count)

        raw = source_score * claim_weight * corroboration
        return round(min(raw, 1.0), 2)

    def passes_threshold(self, credibility_score: float) -> bool:
        """Check if a signal meets the minimum credibility threshold."""
        return credibility_score >= CREDIBILITY_THRESHOLD

    def find_corroborating_signals(
        self,
        title: str,
        entities: list,
        existing_signals: list,
        similarity_threshold: float = 0.55,
    ) -> list:
        """Find existing signals that corroborate a new signal.

        Uses entity overlap + title similarity to detect same-event coverage.
        Returns list of matching signal IDs.
        """
        matches = []
        title_lower = title.lower()
        entities_set = set(e.lower() for e in (entities or []))

        for signal in existing_signals:
            sig_title = (signal.get("title") or "").lower()
            sig_entities = set(
                e.lower() for e in (signal.get("entities_mentioned") or [])
            )

            # Check entity overlap (at least 2 shared entities)
            entity_overlap = len(entities_set & sig_entities)

            # Check title similarity
            title_sim = SequenceMatcher(None, title_lower, sig_title).ratio()

            # Match if strong entity overlap OR high title similarity
            if entity_overlap >= 2 or title_sim >= similarity_threshold:
                matches.append(signal.get("id"))

        return matches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_credibility_engine.py -v`
Expected: PASS (all 18 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/credibility_engine.py backend/tests/test_credibility_engine.py
git commit -m "feat: add credibility scoring engine — source scores, claim types, corroboration"
```

---

### Task 3: Build Gold Data Feeds (FRED + BSE + RBI Structured)

**Files:**
- Create: `backend/agents/gold_data_feeds.py`
- Create: `backend/tests/test_gold_data_feeds.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gold_data_feeds.py`:

```python
"""Tests for gold-tier data feed clients."""
import pytest
from agents.gold_data_feeds import (
    FREDClient,
    BSEAnnouncementsFetcher,
    RBIStructuredDataFetcher,
    FRED_SERIES,
    FRED_INDIA_IMPACT,
)


# ── FRED Client Tests ────────────────────────────────────────────────────────

def test_fred_series_defined():
    """FRED should track key US economic indicators."""
    assert "GDP" in FRED_SERIES
    assert "UNRATE" in FRED_SERIES
    assert "CPIAUCSL" in FRED_SERIES
    assert "DFF" in FRED_SERIES
    assert "T10Y2Y" in FRED_SERIES


def test_fred_india_impact_mapping():
    """Each FRED series should have an India impact description."""
    for series_id in FRED_SERIES:
        assert series_id in FRED_INDIA_IMPACT, f"Missing India impact for {series_id}"


def test_fred_client_init():
    client = FREDClient(api_key="test_key")
    assert client.api_key == "test_key"
    assert client.base_url == "https://api.stlouisfed.org/fred"


def test_fred_client_no_key():
    """FRED client should handle missing API key gracefully."""
    client = FREDClient(api_key=None)
    assert client.api_key is None


def test_fred_build_signal_from_data():
    """FRED data should produce a properly structured signal dict."""
    client = FREDClient(api_key="test")
    signal = client.build_signal(
        series_id="UNRATE",
        value=4.2,
        prev_value=3.9,
        date="2026-03-01",
    )
    assert signal["source"] == "FRED"
    assert signal["source_tier"] == 1
    assert signal["signal_type"] == "monetary"
    assert "unemployment" in signal["title"].lower() or "UNRATE" in signal["title"]
    assert signal["india_impact_reasoning"] is not None


# ── BSE Announcements Tests ──────────────────────────────────────────────────

def test_bse_fetcher_init():
    fetcher = BSEAnnouncementsFetcher()
    assert fetcher.base_url == "https://api.bseindia.com/BseIndiaAPI/api"


def test_bse_announcement_categories():
    """BSE fetcher should track important announcement types."""
    fetcher = BSEAnnouncementsFetcher()
    assert "Board Meeting" in fetcher.important_categories
    assert "Financial Results" in fetcher.important_categories
    assert "Insider Trading" in fetcher.important_categories


# ── RBI Structured Data Tests ────────────────────────────────────────────────

def test_rbi_fetcher_init():
    fetcher = RBIStructuredDataFetcher()
    assert fetcher.base_url is not None


def test_rbi_data_points():
    """RBI fetcher should track key monetary data points."""
    fetcher = RBIStructuredDataFetcher()
    assert "repo_rate" in fetcher.data_points
    assert "forex_reserves" in fetcher.data_points
    assert "cpi_inflation" in fetcher.data_points
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_gold_data_feeds.py -v`
Expected: FAIL — `No module named 'agents.gold_data_feeds'`

- [ ] **Step 3: Implement gold data feeds**

Create `backend/agents/gold_data_feeds.py`:

```python
"""
Gold-Tier Data Feeds — Structured, Authoritative, Free

1. FREDClient          — US Federal Reserve Economic Data (free API key)
2. BSEAnnouncementsFetcher — BSE corporate announcements (no key needed)
3. RBIStructuredDataFetcher — RBI monetary data (no key needed)

All sources are government/regulatory — highest credibility tier.
"""
import os
import httpx
import structlog
from datetime import datetime, timedelta
from typing import Optional

logger = structlog.get_logger()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# ── FRED Series Definitions ──────────────────────────────────────────────────
# Key US economic indicators that directly impact Indian markets

FRED_SERIES = {
    "GDP":       "US Gross Domestic Product",
    "UNRATE":    "US Unemployment Rate",
    "CPIAUCSL":  "US Consumer Price Index (Inflation)",
    "DFF":       "Federal Funds Effective Rate",
    "T10Y2Y":    "10Y-2Y Treasury Spread (Recession Indicator)",
    "DTWEXBGS":  "Trade Weighted US Dollar Index",
    "BAMLH0A0HYM2": "US High Yield Bond Spread (Risk Appetite)",
}

FRED_INDIA_IMPACT = {
    "GDP":       "US GDP growth drives global risk appetite. Strong US GDP = FII inflows to India. Weak = outflows.",
    "UNRATE":    "Rising US unemployment → Fed rate cuts expected → Positive for Indian equities via FII flows.",
    "CPIAUCSL":  "US inflation above 3% → Fed stays hawkish → Strong dollar → INR pressure + FII outflows from India.",
    "DFF":       "Fed funds rate directly sets global cost of capital. Higher rate = capital flight from India to US treasuries.",
    "T10Y2Y":    "Yield curve inversion (negative) = US recession signal → Risk-off globally → FII selling in India.",
    "DTWEXBGS":  "Strong dollar index = INR weakening + import cost rise + current account deficit pressure for India.",
    "BAMLH0A0HYM2": "Widening credit spreads = risk-off environment → FII outflows from emerging markets including India.",
}

FRED_SIGNAL_TYPES = {
    "GDP":       "fiscal",
    "UNRATE":    "monetary",
    "CPIAUCSL":  "monetary",
    "DFF":       "monetary",
    "T10Y2Y":    "monetary",
    "DTWEXBGS":  "currency",
    "BAMLH0A0HYM2": "monetary",
}


# ═════════════════════════════════════════════════════════════════════════════
# 1. FRED CLIENT — US Federal Reserve Economic Data
# ═════════════════════════════════════════════════════════════════════════════

class FREDClient:
    """Fetches key US economic indicators from FRED API.

    Free API key required — register at https://fred.stlouisfed.org/docs/api/api_key.html
    Rate limit: 120 requests per minute (generous).
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self.base_url = "https://api.stlouisfed.org/fred"

    async def fetch_latest(self, series_id: str) -> Optional[dict]:
        """Fetch the most recent observation for a FRED series."""
        if not self.api_key:
            logger.warning("fred.no_api_key", series=series_id)
            return None

        url = f"{self.base_url}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2,  # latest + previous for comparison
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, params=params)
                if r.status_code == 200:
                    data = r.json()
                    observations = data.get("observations", [])
                    if len(observations) >= 2:
                        return {
                            "series_id": series_id,
                            "name": FRED_SERIES.get(series_id, series_id),
                            "value": float(observations[0]["value"]),
                            "prev_value": float(observations[1]["value"]),
                            "date": observations[0]["date"],
                            "prev_date": observations[1]["date"],
                        }
                    elif len(observations) == 1:
                        return {
                            "series_id": series_id,
                            "name": FRED_SERIES.get(series_id, series_id),
                            "value": float(observations[0]["value"]),
                            "prev_value": None,
                            "date": observations[0]["date"],
                            "prev_date": None,
                        }
        except Exception as e:
            logger.warning("fred.fetch_error", series=series_id, error=str(e))
        return None

    async def fetch_all_indicators(self) -> list:
        """Fetch latest data for all tracked FRED series."""
        results = []
        for series_id in FRED_SERIES:
            data = await self.fetch_latest(series_id)
            if data:
                results.append(data)
        return results

    def build_signal(
        self,
        series_id: str,
        value: float,
        prev_value: float,
        date: str,
    ) -> dict:
        """Convert a FRED data point into an InvestAI signal dict."""
        name = FRED_SERIES.get(series_id, series_id)

        # Determine sentiment from direction of change
        if prev_value is not None and prev_value != 0:
            change_pct = ((value - prev_value) / abs(prev_value)) * 100
            direction = "rose" if change_pct > 0 else "fell"
            title = f"{name}: {direction} to {value} ({change_pct:+.1f}%)"
        else:
            change_pct = 0
            title = f"{name}: Latest reading at {value}"

        # Determine importance based on change magnitude
        abs_change = abs(change_pct)
        if abs_change > 10:
            importance = 9.0
        elif abs_change > 5:
            importance = 8.0
        elif abs_change > 2:
            importance = 7.0
        elif abs_change > 0.5:
            importance = 6.0
        else:
            importance = 4.0

        return {
            "title": title[:100],
            "content": f"{name} ({series_id}): Value={value}, Previous={prev_value}, Date={date}. {FRED_INDIA_IMPACT.get(series_id, '')}",
            "source": "FRED",
            "source_tier": 1,
            "signal_type": FRED_SIGNAL_TYPES.get(series_id, "monetary"),
            "urgency": "breaking" if abs_change > 5 else "developing",
            "importance_score": importance,
            "confidence": 0.95,  # Government data = high confidence
            "geography": "us",
            "sentiment": "negative" if change_pct > 0 and series_id in ("UNRATE", "CPIAUCSL", "DFF") else "positive" if change_pct > 0 else "neutral",
            "entities_mentioned": ["Federal Reserve", "US Economy", series_id],
            "india_impact": "high" if series_id in ("DFF", "T10Y2Y", "DTWEXBGS") else "medium",
            "india_impact_reasoning": FRED_INDIA_IMPACT.get(series_id, ""),
            "claim_type": "factual",  # Government data is always factual
            "data_source": "FRED API",
        }


# ═════════════════════════════════════════════════════════════════════════════
# 2. BSE CORPORATE ANNOUNCEMENTS
# ═════════════════════════════════════════════════════════════════════════════

class BSEAnnouncementsFetcher:
    """Fetches corporate announcements from BSE India API.

    No API key needed. Covers board meetings, financial results,
    insider trading disclosures, and corporate actions.
    """

    def __init__(self):
        self.base_url = "https://api.bseindia.com/BseIndiaAPI/api"
        self.important_categories = [
            "Board Meeting",
            "Financial Results",
            "Insider Trading",
            "Corporate Action",
            "Acquisition",
            "Change in Directors",
            "Credit Rating",
        ]

    async def fetch_recent_announcements(self, hours: int = 24) -> list:
        """Fetch corporate announcements from the last N hours."""
        log = logger.bind(action="bse_announcements")
        url = f"{self.base_url}/AnnGetData"

        today = datetime.now().strftime("%Y%m%d")
        params = {
            "strCat": "-1",  # All categories
            "strPrevDate": today,
            "strScrip": "",
            "strSearch": "P",
            "strVal": "0",
            "strType": "C",
        }

        try:
            async with httpx.AsyncClient(
                headers={**HEADERS, "Referer": "https://www.bseindia.com/"},
                timeout=15,
            ) as client:
                r = await client.get(url, params=params)
                if r.status_code == 200:
                    data = r.json()
                    announcements = data.get("Table", [])

                    # Filter to important categories
                    important = []
                    for ann in announcements:
                        cat = ann.get("CATEGORYNAME", "")
                        if any(imp_cat.lower() in cat.lower() for imp_cat in self.important_categories):
                            important.append({
                                "title": ann.get("NEWSSUB", "")[:100],
                                "company": ann.get("SLONGNAME", ""),
                                "symbol": ann.get("SCRIP_CD", ""),
                                "category": cat,
                                "date": ann.get("NEWS_DT", ""),
                                "content": ann.get("NEWSSUB", ""),
                                "attachment_url": ann.get("ATTACHMENTNAME", ""),
                            })

                    log.info("bse.fetched", total=len(announcements), important=len(important))
                    return important
                else:
                    log.warning("bse.bad_status", status=r.status_code)
        except Exception as e:
            log.warning("bse.error", error=str(e))
        return []

    def build_signal(self, announcement: dict) -> dict:
        """Convert a BSE announcement into an InvestAI signal dict."""
        category = announcement.get("category", "")
        company = announcement.get("company", "")
        title = announcement.get("title", "")

        # Score importance by category
        importance_map = {
            "Financial Results": 8.0,
            "Board Meeting": 7.0,
            "Insider Trading": 8.5,
            "Credit Rating": 7.5,
            "Acquisition": 8.0,
            "Corporate Action": 6.5,
            "Change in Directors": 5.5,
        }
        importance = importance_map.get(category, 5.0)

        return {
            "title": f"BSE: {company} — {title}"[:100],
            "content": f"{company}: {title} (Category: {category})",
            "source": "BSE Announcements",
            "source_tier": 1,
            "signal_type": "corporate",
            "urgency": "breaking" if category in ("Financial Results", "Insider Trading") else "developing",
            "importance_score": importance,
            "confidence": 0.95,
            "geography": "india",
            "sentiment": "neutral",
            "entities_mentioned": [company, category],
            "india_impact": "high",
            "india_impact_reasoning": f"Direct corporate disclosure from {company} on BSE",
            "claim_type": "factual",
            "data_source": "BSE India API",
        }


# ═════════════════════════════════════════════════════════════════════════════
# 3. RBI STRUCTURED DATA
# ═════════════════════════════════════════════════════════════════════════════

class RBIStructuredDataFetcher:
    """Fetches structured monetary data from RBI.

    Tracks repo rate, forex reserves, CPI inflation, and other key
    monetary indicators. No API key needed.
    """

    def __init__(self):
        self.base_url = "https://rbi.org.in"
        self.data_points = {
            "repo_rate":       {"description": "RBI Repo Rate", "url_path": "/scripts/bs_viewcontent.aspx?Id=2147"},
            "forex_reserves":  {"description": "India Forex Reserves", "url_path": "/scripts/WSSViewDetail.aspx?TYPE=Section&PARAM1=2"},
            "cpi_inflation":   {"description": "Consumer Price Index", "url_path": "/scripts/PublicationsView.aspx?id=22427"},
            "credit_growth":   {"description": "Bank Credit Growth", "url_path": "/scripts/PublicationsView.aspx?id=22308"},
            "money_supply":    {"description": "Money Supply (M3)", "url_path": "/scripts/PublicationsView.aspx?id=22309"},
        }

    async def fetch_key_rates(self) -> dict:
        """Fetch current RBI key rates from the RBI website."""
        log = logger.bind(action="rbi_rates")
        url = f"{self.base_url}/scripts/bs_viewcontent.aspx?Id=2147"

        try:
            async with httpx.AsyncClient(
                headers={**HEADERS, "Referer": "https://rbi.org.in/"},
                timeout=15,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    # Parse the RBI rates page — extract key rates
                    text = r.text
                    rates = {
                        "repo_rate": self._extract_rate(text, "Repo Rate"),
                        "reverse_repo_rate": self._extract_rate(text, "Reverse Repo Rate"),
                        "bank_rate": self._extract_rate(text, "Bank Rate"),
                        "crr": self._extract_rate(text, "CRR"),
                        "slr": self._extract_rate(text, "SLR"),
                        "fetched_at": datetime.utcnow().isoformat(),
                        "source": "RBI Official Website",
                    }
                    log.info("rbi.rates_fetched", rates=rates)
                    return rates
        except Exception as e:
            log.warning("rbi.rates_error", error=str(e))

        return {
            "error": "Could not fetch RBI rates",
            "fetched_at": datetime.utcnow().isoformat(),
        }

    async def fetch_forex_reserves(self) -> dict:
        """Fetch latest forex reserve data from RBI."""
        log = logger.bind(action="rbi_forex")
        url = f"{self.base_url}/scripts/WSSViewDetail.aspx?TYPE=Section&PARAM1=2"

        try:
            async with httpx.AsyncClient(
                headers={**HEADERS, "Referer": "https://rbi.org.in/"},
                timeout=15,
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return {
                        "raw_html_length": len(r.text),
                        "fetched_at": datetime.utcnow().isoformat(),
                        "source": "RBI Weekly Statistical Supplement",
                        "note": "Parse HTML for latest forex reserve figures",
                    }
        except Exception as e:
            log.warning("rbi.forex_error", error=str(e))

        return {"error": "Could not fetch forex reserves"}

    def _extract_rate(self, html: str, rate_name: str) -> Optional[str]:
        """Simple extraction of rate value from RBI HTML page."""
        import re
        pattern = rf"{re.escape(rate_name)}.*?(\d+\.?\d*)\s*%"
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            return f"{match.group(1)}%"
        return None

    def build_signal(self, data_point: str, value: str, prev_value: str = None) -> dict:
        """Convert an RBI data point into an InvestAI signal dict."""
        description = self.data_points.get(data_point, {}).get("description", data_point)

        title = f"RBI: {description} at {value}"
        if prev_value:
            title = f"RBI: {description} changed from {prev_value} to {value}"

        return {
            "title": title[:100],
            "content": f"RBI {description}: {value}. Previous: {prev_value or 'N/A'}",
            "source": "RBI Data",
            "source_tier": 1,
            "signal_type": "monetary",
            "urgency": "developing",
            "importance_score": 8.5,
            "confidence": 0.95,
            "geography": "india",
            "sentiment": "neutral",
            "entities_mentioned": ["RBI", description],
            "india_impact": "high",
            "india_impact_reasoning": f"Direct RBI monetary data — {description} directly affects banking, liquidity, and market rates",
            "claim_type": "factual",
            "data_source": "RBI Official Data",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_gold_data_feeds.py -v`
Expected: PASS (all 12 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agents/gold_data_feeds.py backend/tests/test_gold_data_feeds.py
git commit -m "feat: add gold-tier data feeds — FRED API, BSE announcements, RBI structured data"
```

---

### Task 4: Add Google News RSS + Integrate Credibility into Signal Watcher

**Files:**
- Modify: `backend/agents/signal_watcher.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_signal_watcher_credibility.py`:

```python
"""Tests for credibility integration in signal watcher."""
import pytest
from agents.signal_watcher import RSS_SOURCES, SIGNAL_CLASSIFIER_PROMPT


def test_google_news_rss_exists():
    """Google News RSS should be in the source list for corroboration."""
    names = [s["name"] for s in RSS_SOURCES]
    assert "Google News Business" in names


def test_google_news_is_tier3():
    """Google News should be tier 3 (silver, used for corroboration)."""
    gn = next(s for s in RSS_SOURCES if s["name"] == "Google News Business")
    assert gn["tier"] == 3


def test_classifier_prompt_includes_claim_type():
    """The signal classifier should extract claim_type."""
    assert "claim_type" in SIGNAL_CLASSIFIER_PROMPT


def test_pib_rss_exists():
    """PIB (Press Information Bureau) RSS should be in sources."""
    names = [s["name"] for s in RSS_SOURCES]
    # PIB is already there as "Ministry of Finance" — verify it
    assert "Ministry of Finance" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_signal_watcher_credibility.py -v`
Expected: FAIL — `Google News Business` not in source list, `claim_type` not in prompt

- [ ] **Step 3: Add Google News RSS to sources**

In `backend/agents/signal_watcher.py`, add to `RSS_SOURCES` after the Tier 3 section:

```python
    # ── SILVER: Aggregators (for corroboration, not primary trust) ────────────
    {"url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pKVGlnQVAB?hl=en-IN&gl=IN&ceid=IN:en", "name": "Google News Business", "tier": 3, "region": "india"},
    {"url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en", "name": "Google News Finance US", "tier": 3, "region": "us"},
```

- [ ] **Step 4: Add claim_type to the classifier prompt**

In `backend/agents/signal_watcher.py`, update `SIGNAL_CLASSIFIER_PROMPT` to add `claim_type` to the JSON output. Replace the existing JSON template in the prompt with:

```python
SIGNAL_CLASSIFIER_PROMPT = """You are a financial signal extractor specializing in Indian markets.

Analyze this content and extract structured signal data.

Content: {content}
Source: {source}
Source Tier: {tier}
Source Region: {region}

Extract and return ONLY valid JSON (no markdown, no preamble):
{{
  "title": "concise signal title (max 100 chars)",
  "signal_type": "geopolitical|monetary|fiscal|commodity|currency|corporate|natural_disaster|trade",
  "urgency": "breaking|developing|long_term",
  "importance_score": 0.0-10.0,
  "confidence": 0.0-1.0,
  "geography": "global|regional|india|us|europe|china|middle_east",
  "sentiment": "positive|negative|neutral",
  "entities_mentioned": ["Fed", "Oil", "RBI"],
  "sectors_affected": {{
    "aviation": "negative",
    "energy": "positive"
  }},
  "india_impact": "high|medium|low|none",
  "india_impact_reasoning": "Why this affects India specifically",
  "second_order_effects": [
    "Oil spike -> INR depreciation -> FII outflows",
    "Higher input costs -> FMCG margin pressure"
  ],
  "claim_type": "factual|analysis|opinion|tip",
  "requires_immediate_analysis": true
}}

CLAIM TYPE RULES:
- "factual": Verifiable data or confirmed event (e.g., "RBI raised rates by 25bps", "Q3 revenue was 5000cr")
- "analysis": Informed reasoning about future impact (e.g., "markets may fall due to...")
- "opinion": Subjective view without data backing (e.g., "I think Reliance will...")
- "tip": Specific buy/sell recommendation with price targets — ALWAYS flag these

If content has no meaningful financial signal for Indian markets, return:
{{"importance_score": 0, "requires_immediate_analysis": false}}
"""
```

- [ ] **Step 5: Integrate credibility scoring into _scan_rss**

In `backend/agents/signal_watcher.py`, modify the `_scan_rss` method. Add the credibility engine import at the top of the file:

```python
from agents.credibility_engine import CredibilityEngine
```

And in the `__init__` method, add:

```python
        self.credibility = CredibilityEngine()
```

Then in the `_scan_rss` method, after `signal_data = await self._classify_signal(...)` and before creating the Signal object, add credibility scoring:

```python
                # Credibility scoring
                claim_type = signal_data.get("claim_type", "analysis")
                credibility_score = self.credibility.compute_credibility(
                    source_name=source["name"],
                    tier=source["tier"],
                    claim_type=claim_type,
                    corroboration_count=1,  # Will be updated by corroboration check
                )

                # Reject signals that fail credibility threshold
                if not self.credibility.passes_threshold(credibility_score):
                    logger.info("signal_watcher.low_credibility",
                                title=signal_data.get("title", ""),
                                score=credibility_score,
                                claim_type=claim_type)
                    continue
```

And add these fields to the Signal constructor:

```python
                    credibility_score   = credibility_score,
                    claim_type          = claim_type,
                    source_urls         = [entry.get("link", "")],
                    corroboration_count = 1,
```

- [ ] **Step 6: Add corroboration check after full scan**

In `backend/agents/signal_watcher.py`, modify the `scan_all_sources` method to run a corroboration pass after all RSS sources are scanned:

```python
    async def scan_all_sources(self):
        """Full scan of all sources. Called by the background worker."""
        logger.info("signal_watcher.full_scan.start", total_sources=len(RSS_SOURCES))
        new_signals = []

        for source in RSS_SOURCES:
            try:
                signals = await self._scan_rss(source)
                new_signals.extend(signals)
            except Exception as e:
                logger.warning("signal_watcher.rss_error", source=source["name"], error=str(e))

        # ── Corroboration pass: boost signals reported by multiple sources ────
        await self._update_corroboration(new_signals)

        logger.info("signal_watcher.full_scan.complete", new_signals=len(new_signals))
        return new_signals

    async def _update_corroboration(self, new_signals: list):
        """Check new signals against each other and existing signals for corroboration."""
        if len(new_signals) < 2:
            return

        signal_dicts = [
            {
                "id": s.id,
                "title": s.title,
                "entities_mentioned": s.entities_mentioned or [],
            }
            for s in new_signals
        ]

        for signal in new_signals:
            matches = self.credibility.find_corroborating_signals(
                title=signal.title,
                entities=signal.entities_mentioned or [],
                existing_signals=[d for d in signal_dicts if d["id"] != signal.id],
            )

            if matches:
                corroboration_count = len(matches) + 1  # +1 for self
                signal.corroboration_count = corroboration_count
                signal.corroborated_by = matches

                # Recompute credibility with corroboration
                signal.credibility_score = self.credibility.compute_credibility(
                    source_name=signal.source,
                    tier=signal.source_tier,
                    claim_type=signal.claim_type or "analysis",
                    corroboration_count=corroboration_count,
                )

        try:
            await self.db.commit()
        except Exception as e:
            logger.warning("corroboration.commit_failed", error=str(e))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_signal_watcher_credibility.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/agents/signal_watcher.py backend/tests/test_signal_watcher_credibility.py
git commit -m "feat: integrate credibility scoring into signal watcher + add Google News RSS"
```

---

### Task 5: Wire Disconnected Pipes — NSE FII/DII + Gold Feeds into Worker

**Files:**
- Modify: `backend/worker.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_worker_jobs.py`:

```python
"""Tests for worker job definitions."""
import pytest


def test_worker_has_gold_data_job():
    """Worker should have a scheduled job to fetch gold-tier data."""
    from worker import scheduler, start_scheduler
    # Check that the function exists
    from worker import fetch_gold_data
    assert callable(fetch_gold_data)


def test_worker_has_fii_dii_periodic_job():
    """Worker should fetch FII/DII data periodically, not just on advice requests."""
    from worker import fetch_nse_institutional_flows
    assert callable(fetch_nse_institutional_flows)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_worker_jobs.py -v`
Expected: FAIL — `cannot import name 'fetch_gold_data' from 'worker'`

- [ ] **Step 3: Add gold data + FII/DII jobs to worker**

In `backend/worker.py`, add the new job functions and schedule them:

```python
async def fetch_gold_data():
    """Fetch structured data from gold-tier sources (FRED + BSE + RBI).

    Runs every 2 hours. Creates signals from structured data.
    """
    logger.info("worker.gold_data.start")
    try:
        from database.connection import AsyncSessionLocal
        from agents.gold_data_feeds import FREDClient, BSEAnnouncementsFetcher, RBIStructuredDataFetcher
        from agents.credibility_engine import CredibilityEngine
        from models.models import Signal
        from sqlalchemy import select
        import hashlib
        import os

        credibility = CredibilityEngine()

        async with AsyncSessionLocal() as db:
            signals_created = 0

            # ── FRED Data ─────────────────────────────────────────────────────
            fred = FREDClient()
            if fred.api_key:
                indicators = await fred.fetch_all_indicators()
                for indicator in indicators:
                    signal_data = fred.build_signal(
                        series_id=indicator["series_id"],
                        value=indicator["value"],
                        prev_value=indicator.get("prev_value"),
                        date=indicator["date"],
                    )

                    content_hash = hashlib.md5(
                        f"FRED_{indicator['series_id']}_{indicator['date']}".encode()
                    ).hexdigest()

                    existing = await db.execute(
                        select(Signal).where(Signal.content_hash == content_hash)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    cred_score = credibility.compute_credibility(
                        source_name="FRED", tier=1, claim_type="factual", corroboration_count=1
                    )

                    signal = Signal(
                        title=signal_data["title"],
                        content=signal_data["content"],
                        source="FRED",
                        source_agent="gold_data_feeds",
                        source_tier=1,
                        signal_type=signal_data["signal_type"],
                        urgency=signal_data["urgency"],
                        importance_score=signal_data["importance_score"],
                        confidence=signal_data["confidence"],
                        geography=signal_data["geography"],
                        sentiment=signal_data["sentiment"],
                        entities_mentioned=signal_data["entities_mentioned"],
                        india_impact_analysis=signal_data["india_impact_reasoning"],
                        credibility_score=cred_score,
                        claim_type="factual",
                        content_hash=content_hash,
                    )
                    db.add(signal)
                    signals_created += 1

            # ── BSE Announcements ─────────────────────────────────────────────
            bse = BSEAnnouncementsFetcher()
            announcements = await bse.fetch_recent_announcements()
            for ann in announcements[:20]:
                signal_data = bse.build_signal(ann)
                content_hash = hashlib.md5(
                    f"BSE_{ann.get('symbol', '')}_{ann.get('title', '')}".encode()
                ).hexdigest()

                existing = await db.execute(
                    select(Signal).where(Signal.content_hash == content_hash)
                )
                if existing.scalar_one_or_none():
                    continue

                cred_score = credibility.compute_credibility(
                    source_name="BSE Announcements", tier=1, claim_type="factual", corroboration_count=1
                )

                signal = Signal(
                    title=signal_data["title"],
                    content=signal_data["content"],
                    source="BSE Announcements",
                    source_agent="gold_data_feeds",
                    source_tier=1,
                    signal_type="corporate",
                    urgency=signal_data["urgency"],
                    importance_score=signal_data["importance_score"],
                    confidence=0.95,
                    geography="india",
                    entities_mentioned=signal_data["entities_mentioned"],
                    india_impact_analysis=signal_data["india_impact_reasoning"],
                    credibility_score=cred_score,
                    claim_type="factual",
                    content_hash=content_hash,
                )
                db.add(signal)
                signals_created += 1

            if signals_created:
                await db.commit()

            logger.info("worker.gold_data.complete", signals_created=signals_created)

    except Exception as e:
        logger.error("worker.gold_data.error", error=str(e))


async def fetch_nse_institutional_flows():
    """Fetch FII/DII flows from NSE and cache in Redis.

    Runs every 30 minutes during market hours. This data was previously
    only fetched on-demand during advice requests — now it runs periodically
    so every agent has fresh institutional flow data.
    """
    logger.info("worker.fii_dii.start")
    try:
        from agents.data_scrapers import NSEDataScraper
        import redis.asyncio as aioredis
        import os
        import json

        redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        scraper = NSEDataScraper()
        flows = await scraper.fetch_fii_dii_flows()

        if "error" not in flows:
            await redis.setex("fii_dii_flows", 1800, json.dumps(flows))  # 30 min cache
            logger.info("worker.fii_dii.complete",
                        fii=flows.get("fii_net_crores"),
                        dii=flows.get("dii_net_crores"))
        else:
            logger.warning("worker.fii_dii.fetch_failed", error=flows["error"])

        await redis.close()
    except Exception as e:
        logger.error("worker.fii_dii.error", error=str(e))
```

And update `start_scheduler` to add the new jobs:

```python
def start_scheduler():
    scheduler.add_job(scan_signals,                  IntervalTrigger(minutes=15),            id="scan_signals",    replace_existing=True)
    scheduler.add_job(monitor_signal_changes,        IntervalTrigger(minutes=30),            id="signal_monitor",  replace_existing=True)
    scheduler.add_job(fetch_gold_data,               IntervalTrigger(hours=2),               id="gold_data",       replace_existing=True)
    scheduler.add_job(fetch_nse_institutional_flows, IntervalTrigger(minutes=30),            id="fii_dii_flows",   replace_existing=True)
    scheduler.add_job(update_event_lifecycles,       CronTrigger(hour=6, minute=0),          id="lifecycle",       replace_existing=True)
    scheduler.add_job(score_advice_performance,      CronTrigger(day_of_week='sun', hour=2), id="score_advice",    replace_existing=True)
    scheduler.start()
    logger.info("worker.scheduler.started", jobs=[
        "scan_signals(15m)", "signal_monitor(30m)", "gold_data(2h)",
        "fii_dii_flows(30m)", "lifecycle(6am)", "score_advice(sun)"
    ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_worker_jobs.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add backend/worker.py backend/tests/test_worker_jobs.py
git commit -m "feat: wire gold data feeds + FII/DII periodic scraping into worker"
```

---

### Task 6: Wire FII/DII Cache into Signal Watcher Market Snapshot

**Files:**
- Modify: `backend/agents/signal_watcher.py:391-421` (`_get_live_snapshot` method)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_snapshot_fii_dii.py`:

```python
"""Test that market snapshot reads cached FII/DII data."""
import pytest
import json
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_snapshot_reads_cached_fii_dii():
    """Market snapshot should include FII/DII data from Redis cache."""
    from agents.signal_watcher import SignalWatcherAgent

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=lambda key: json.dumps({
        "fii_net_crores": -1500.0,
        "dii_net_crores": 2000.0,
        "net_institutional_flow": 500.0,
        "market_sentiment": "Bullish",
    }).encode() if key == "fii_dii_flows" else None)

    agent = SignalWatcherAgent(db_session=AsyncMock(), redis_client=mock_redis)
    snapshot = await agent._get_live_snapshot()

    assert snapshot["fii_today"]["value"] == -1500.0
    assert snapshot["dii_today"]["value"] == 2000.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_snapshot_fii_dii.py -v`
Expected: FAIL — `fii_today` value is still `None`

- [ ] **Step 3: Update _get_live_snapshot to read cached FII/DII**

In `backend/agents/signal_watcher.py`, modify `_get_live_snapshot()` to read FII/DII data from Redis after fetching Yahoo prices. Replace the static fii/dii lines at the end:

```python
        # Read cached FII/DII flows (populated by worker every 30 min)
        try:
            cached_flows = await self.redis.get("fii_dii_flows") if self.redis else None
            if cached_flows:
                flows = json.loads(cached_flows)
                snapshot["fii_today"] = {"value": flows.get("fii_net_crores"), "unit": "crore INR", "source": "NSE Live"}
                snapshot["dii_today"] = {"value": flows.get("dii_net_crores"), "unit": "crore INR", "source": "NSE Live"}
                snapshot["institutional_sentiment"] = flows.get("market_sentiment", "unknown")
            else:
                snapshot["fii_today"] = {"value": None, "unit": "crore INR", "note": "Waiting for NSE data"}
                snapshot["dii_today"] = {"value": None, "unit": "crore INR", "note": "Waiting for NSE data"}
        except Exception:
            snapshot["fii_today"] = {"value": None, "unit": "crore INR", "note": "FII data unavailable"}
            snapshot["dii_today"] = {"value": None, "unit": "crore INR", "note": "DII data unavailable"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /workspaces/investai/backend && python -m pytest tests/test_snapshot_fii_dii.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/signal_watcher.py backend/tests/test_snapshot_fii_dii.py
git commit -m "feat: wire cached FII/DII flows into market snapshot"
```

---

### Task 7: Update .env.example with New API Keys

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add FRED API key to .env.example**

Add to `.env.example`:

```bash
# ── Gold Data Feeds ──────────────────────────────────────────────────────────
# FRED API (US Federal Reserve Economic Data) — free key from https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY=your_fred_api_key_here
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add FRED_API_KEY to .env.example"
```

---

### Task 8: Run All Tests + Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd /workspaces/investai/backend && python -m pytest tests/ -v`
Expected: All tests pass (existing 24 + new ~35 = ~59 total)

- [ ] **Step 2: Verify imports work**

Run:
```bash
cd /workspaces/investai/backend && python -c "
from agents.credibility_engine import CredibilityEngine
from agents.gold_data_feeds import FREDClient, BSEAnnouncementsFetcher, RBIStructuredDataFetcher
from agents.signal_watcher import SignalWatcherAgent, RSS_SOURCES
print(f'RSS sources: {len(RSS_SOURCES)}')
print(f'Credibility engine: OK')
print(f'Gold feeds: OK')
engine = CredibilityEngine()
score = engine.compute_credibility('RBI', 1, 'factual', 3)
print(f'RBI factual corroborated score: {score}')
"
```
Expected: Prints source count (27+), engine OK, score = 1.0

- [ ] **Step 3: Run Alembic migration**

Run: `cd /workspaces/investai/backend && alembic upgrade head`
Expected: Migration 005 applies cleanly

- [ ] **Step 4: Final commit — merge all work**

```bash
git add -A
git commit -m "feat: data quality engine — gold sources, credibility scoring, pipe fixes

- Added FRED API client (7 US economic indicators with India impact)
- Added BSE corporate announcements fetcher (earnings, insider trading, board meetings)
- Added RBI structured data fetcher (repo rate, forex reserves, CPI)
- Added Google News RSS for signal corroboration
- Built credibility scoring engine (source score × claim weight × corroboration)
- Signals below 0.5 credibility are filtered out of the pipeline
- Wired NSE FII/DII scraper into periodic worker (was only on-demand before)
- Wired FII/DII cache into market snapshot (agents now see live institutional flows)
- Added credibility_score, claim_type, source_urls, corroboration_count to Signal model
- New alembic migration 005 for credibility columns"
```
