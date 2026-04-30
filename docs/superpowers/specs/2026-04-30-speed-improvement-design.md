# Speed Improvement Design — Cut Response Time from 24 min → 15-16 min

**Date:** 2026-04-30  
**Scope:** Backend pipeline only. No frontend changes. No quality trade-off.  
**Target:** ~15-16 min total (down from ~24 min)

---

## Problem

The InvestAI pipeline makes 22 LLM calls at 60-80s each on OpenRouter (Kimi K2.6). Three of those calls produce no analytical value — they exist only for formatting or routing that code can do directly. Removing them saves ~8-10 minutes with zero effect on output quality.

---

## Changes

### Change 1 — Remove orchestrator LLM planning (~2 min saved)

**File:** `backend/agents/orchestrator.py`

**Current behaviour:** When a query arrives, the orchestrator calls the LLM to decide which agents to run. The LLM always returns the same agent list regardless of query.

**New behaviour:** Replace the LLM planning call with a deterministic code-based router. The router checks query type (already classified by `RecommendationPolicy`) and returns a pre-defined agent list for each type:

| Query type | Agents to run |
|---|---|
| `stock_inquiry` | signal_watcher, research_agent, company_intelligence, plain_formatter |
| `market_analysis` | signal_watcher, research_agent, temporal_agent, company_intelligence, investment_manager, plain_formatter |
| `portfolio_review` | signal_watcher, research_agent, portfolio_agent + investment_manager (merged), plain_formatter |
| default | full pipeline |

The `_execute_task_plan` method stays intact — we just replace the LLM call that generates the plan with a static lookup.

---

### Change 2 — Remove LLM from market intelligence (~3-4 min saved)

**File:** `backend/agents/market_intelligence.py`

**Current behaviour:** `get_full_intelligence` collects raw market data (Nifty, VIX, FII/DII flows, crude, USD/INR) then passes it through 3 LLM calls that format/interpret the numbers into structured dicts.

**New behaviour:** Remove the 3 LLM formatting calls. Pass the raw data dicts directly to downstream agents (ResearchAgent, CompanyIntelligence). These agents already parse raw numbers — they do not depend on the LLM-formatted version.

The `get_full_intelligence` function becomes a pure data collector: fetch → aggregate → return. No LLM involved.

---

### Change 3 — Merge PortfolioAgent + InvestmentManagerAgent (~1-2 min saved)

**Files:** `backend/agents/agents_impl.py`, `backend/agents/company_intelligence.py`

**Current behaviour:** PortfolioAgent runs first (1 LLM call → strategy signals + sector allocation). Its output is passed to InvestmentManagerAgent (1 LLM call → educational context + monitoring framework). Two sequential calls, each dependent on the previous.

**New behaviour:** Merge into a single `PortfolioStrategyAgent` that runs one LLM call with a combined prompt. The combined prompt asks for:
- Sector BUY/AVOID signals with confidence% and invalidation conditions (was PortfolioAgent)
- Strategy context + monitoring framework + risk awareness (was InvestmentManagerAgent)

Output keys from both agents are preserved so nothing downstream breaks. The orchestrator treats it as one agent step.

---

## What does NOT change

- All agent prompts for ResearchAgent, CompanyIntelligence, PlainFormatter — unchanged
- SEBI Option 1 compliance — unchanged
- Signal card output format (BUY/AVOID/NEUTRAL + confidence + evidence + invalidation) — unchanged
- max_tokens per agent — unchanged (kept at 8192 — reducing this is deferred)
- Error handling / try-except fallbacks — unchanged
- All async/await and asyncio.wait_for timeouts — unchanged

---

## Expected result

| Metric | Before | After |
|---|---|---|
| Total response time | ~24 min | ~15-16 min |
| LLM calls | 22 | 18-19 |
| Output quality | baseline | identical |
| Risk | — | low |

---

## Out of scope

- max_tokens reduction (Change 4) — deferred, requires per-agent testing
- Streaming / partial results — requires frontend changes
- Redis caching of market intelligence — can be added later as a separate change
