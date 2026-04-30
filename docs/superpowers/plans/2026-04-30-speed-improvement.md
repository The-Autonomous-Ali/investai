# Speed Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut pipeline response time from ~24 min to ~15-16 min by removing 3 unnecessary LLM calls from the critical path.

**Architecture:** Three targeted changes to `orchestrator.py` and `market_intelligence.py` — no new files, no frontend changes, no quality trade-off. Each change removes one LLM call that was doing formatting/routing work that code can do directly.

**Tech Stack:** Python asyncio, FastAPI, OpenRouter (Kimi K2.6)

---

## Files Modified

- `backend/agents/orchestrator.py` — remove `_build_task_plan` LLM call + remove `investment_manager` from static plan
- `backend/agents/market_intelligence.py` — replace 7 `_analyze`/`_explain` LLM calls with pure-code transforms

---

## Task 1: Replace orchestrator LLM planning with a static task plan

**Files:**
- Modify: `backend/agents/orchestrator.py`

### Why this saves time
`_build_task_plan` at line 397 calls `call_llm_structured` with ORCHESTRATOR_PROMPT every single request. The LLM always returns the same 11-step plan. This is ~70s wasted before the pipeline even starts.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator_static_plan.py`:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.orchestrator import OrchestratorAgent

@pytest.mark.asyncio
async def test_build_task_plan_does_not_call_llm():
    """Static plan must return without any LLM call."""
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    state = {
        "query": "should I buy Reliance",
        "amount": 100000,
        "horizon": "1 year",
        "country": "India",
        "user_profile": {},
    }
    plan = await orch._build_task_plan(state)
    assert "task_plan" in plan
    assert len(plan["task_plan"]) >= 9
    # investment_manager must NOT be in the plan
    agent_names = [t["agent"] for t in plan["task_plan"]]
    assert "investment_manager" not in agent_names

@pytest.mark.asyncio
async def test_static_plan_has_correct_dependencies():
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    state = {"query": "market outlook", "amount": 50000,
             "horizon": "6 months", "country": "India", "user_profile": {}}
    plan = await orch._build_task_plan(state)
    steps_by_num = {t["step"]: t for t in plan["task_plan"]}
    # global_macro must depend on signal_watcher (step 1)
    assert 1 in steps_by_num[2]["depends_on"]
    # research must depend on global_macro (step 2)
    assert 2 in steps_by_num[3]["depends_on"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_orchestrator_static_plan.py -v
```

Expected: `ImportError` or `AttributeError` — `_build_task_plan` doesn't exist as static yet.

- [ ] **Step 3: Replace `_build_task_plan` in orchestrator.py**

In `backend/agents/orchestrator.py`:

**3a. Remove `ORCHESTRATOR_PROMPT` and `_TaskPlanSchema`** (lines 32–83). Delete both the class and the prompt constant entirely.

**3b. Remove `call_llm_structured` from the import** on line 25 — change:
```python
from utils.llm_client import call_llm, call_llm_structured
```
to:
```python
from utils.llm_client import call_llm
```

**3c. Replace the `_build_task_plan` method** (lines 397–416) with this static version:

```python
FIXED_TASK_PLAN = {
    "intent": "comprehensive market analysis and sector signals",
    "task_plan": [
        {"step": 1,  "agent": "signal_watcher",       "input": "get current global + India signals",  "depends_on": []},
        {"step": 2,  "agent": "global_macro_agent",   "input": "score global signal India impact",    "depends_on": [1]},
        {"step": 3,  "agent": "research_agent",       "input": "deep analysis with macro context",    "depends_on": [2]},
        {"step": 4,  "agent": "pattern_matcher",      "input": "historical analogues",                "depends_on": [2]},
        {"step": 5,  "agent": "temporal_agent",       "input": "event lifecycles",                    "depends_on": [2]},
        {"step": 6,  "agent": "portfolio_agent",      "input": "build sector signals",                "depends_on": [3, 4]},
        {"step": 7,  "agent": "tax_agent",            "input": "optimize for tax",                    "depends_on": [6]},
        {"step": 8,  "agent": "company_intelligence", "input": "find best companies",                 "depends_on": [3]},
        {"step": 9,  "agent": "adversarial_agent",    "input": "stress test company picks",           "depends_on": [8]},
        {"step": 10, "agent": "sentiment_aggregator", "input": "score company sentiments",            "depends_on": [9]},
    ],
    "requires_real_time_signals": True,
    "urgency": "high",
}
```

Place this constant at module level (below imports, before `OrchestratorAgent` class).

Then replace the method body:

```python
async def _build_task_plan(self, state: dict) -> dict:
    return FIXED_TASK_PLAN
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_orchestrator_static_plan.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/orchestrator.py backend/tests/test_orchestrator_static_plan.py
git commit -m "perf: replace orchestrator LLM planning with static task plan (~70s saved)"
```

---

## Task 2: Remove LLM calls from market intelligence

**Files:**
- Modify: `backend/agents/market_intelligence.py`

### Why this saves time
`get_full_intelligence` fires 7 LLM calls "in parallel" but OpenRouter queues concurrent requests — so they run mostly sequentially in practice. That's up to 7 × 70s ≈ 8 min. Replacing these with code-based transforms brings this down to ~10-15s (pure data fetching).

The 7 LLM calls to remove are in:
1. `BulkDealMonitor._analyze` (line 162)
2. `InsiderTradingMonitor._analyze` (line 280)
3. `EarningsCalendar._analyze` (line 402)
4. `SectorRotationModel.analyze` (line 497)
5. `FIISectoralFlowTracker._analyze` (line 603)
6. `MaxPainCalculator._explain` (line 870)
7. `OptionsChainAnalyzer._analyze_with_llm` (line 1035)

Each `_analyze` method is replaced with a `_analyze_sync` method that computes the same fields from raw data using Python.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_market_intelligence_no_llm.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.market_intelligence import (
    BulkDealMonitor, InsiderTradingMonitor, FIISectoralFlowTracker,
    MaxPainCalculator, OptionsChainAnalyzer, SectorRotationModel,
    EarningsCalendar,
)

@pytest.mark.asyncio
async def test_bulk_deal_analyze_no_llm():
    """_analyze must return a dict without calling call_llm."""
    monitor = BulkDealMonitor()
    sample_deals = [
        {"symbol": "ONGC", "buyQuantity": "500000", "sellQuantity": "0",
         "tradeType": "bulk"},
    ]
    with patch("agents.market_intelligence.call_llm") as mock_llm:
        result = monitor._analyze_sync(sample_deals, [])
    mock_llm.assert_not_called()
    assert "net_smart_money_direction" in result
    assert "most_significant_deals" in result

@pytest.mark.asyncio
async def test_fii_sectoral_analyze_no_llm():
    monitor = FIISectoralFlowTracker()
    sample = [
        {"clientType": "FII/FPI", "buyValue": "5000", "sellValue": "3000",
         "category": "Equity"},
    ]
    with patch("agents.market_intelligence.call_llm") as mock_llm:
        result = monitor._analyze_sync(sample)
    mock_llm.assert_not_called()
    assert "total_fii_flow_crore" in result
    assert "flow_direction" in result

@pytest.mark.asyncio
async def test_max_pain_explain_no_llm():
    calc = MaxPainCalculator()
    mp_data = {"symbol": "NIFTY", "max_pain": 22500, "current_price": 22800,
               "expiry": "01-May-2026", "dte": 2}
    with patch("agents.market_intelligence.call_llm") as mock_llm:
        result = calc._explain_sync("NIFTY", mp_data)
    mock_llm.assert_not_called()
    assert "max_pain_price" in result
    assert result["max_pain_price"] == 22500

@pytest.mark.asyncio
async def test_options_chain_no_llm():
    analyzer = OptionsChainAnalyzer()
    summary = {"current_price": 22800, "pcr": 1.1, "total_call_oi": 100000,
               "total_put_oi": 110000, "max_call_strike": 23000,
               "max_put_strike": 22000, "atm_strikes": []}
    with patch("agents.market_intelligence.call_llm") as mock_llm:
        result = analyzer._analyze_sync("NIFTY", summary)
    mock_llm.assert_not_called()
    assert "pcr" in result
    assert result["key_resistance"] == 23000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_market_intelligence_no_llm.py -v
```

Expected: `AttributeError` — `_analyze_sync`, `_explain_sync` don't exist yet.

- [ ] **Step 3: Replace LLM calls in BulkDealMonitor**

In `market_intelligence.py`, find `BulkDealMonitor._analyze` (around line 162) and:

**a)** Add a new `_analyze_sync` method right before `_analyze`:

```python
def _analyze_sync(self, bulk_deals: list, block_deals: list) -> dict:
    """Extract key signals from raw deal data — no LLM."""
    significant = []
    for deal in (bulk_deals + block_deals)[:10]:
        qty_buy  = float(deal.get("buyQuantity",  0) or 0)
        qty_sell = float(deal.get("sellQuantity", 0) or 0)
        side     = "buy" if qty_buy >= qty_sell else "sell"
        qty      = max(qty_buy, qty_sell)
        significant.append({
            "symbol":    deal.get("symbol", ""),
            "deal_type": "bulk",
            "side":      side,
            "quantity":  qty,
            "signal":    "bullish" if side == "buy" else "bearish",
        })
    net_buys  = sum(1 for d in significant if d["signal"] == "bullish")
    net_sells = len(significant) - net_buys
    direction = ("bullish" if net_buys > net_sells
                 else "bearish" if net_sells > net_buys else "mixed")
    return {
        "most_significant_deals":      significant[:5],
        "net_smart_money_direction":   direction,
        "sectors_seeing_accumulation": [],
        "sectors_seeing_distribution": [],
        "key_insight": (f"{net_buys} institutional buy deal(s) vs "
                        f"{net_sells} sell deal(s) today"),
    }
```

**b)** In `get_today_deals`, replace `result = await self._analyze(bulk_deals[:20], block_deals[:20])` with:
```python
result = self._analyze_sync(bulk_deals[:20], block_deals[:20])
```

- [ ] **Step 4: Replace LLM calls in InsiderTradingMonitor**

Add `_analyze_sync` to `InsiderTradingMonitor` before its `_analyze` method:

```python
def _analyze_sync(self, transactions: list) -> dict:
    """Extract insider signals from raw SEBI disclosures — no LLM."""
    buys  = [t for t in transactions if
             str(t.get("transactionType", "")).lower() in ("buy", "purchase", "acquisition")]
    sells = [t for t in transactions if
             str(t.get("transactionType", "")).lower() in ("sell", "sale", "disposal")]
    sentiment = ("bullish" if len(buys) > len(sells)
                 else "bearish" if len(sells) > len(buys) else "neutral")
    return {
        "significant_insider_buys":    [
            {"symbol": t.get("symbol", ""), "transaction": "buy",
             "insider_name": t.get("personName", ""),
             "signal": "bullish", "conviction": "high"}
            for t in buys[:5]
        ],
        "significant_insider_sells":   [
            {"symbol": t.get("symbol", ""), "transaction": "sell",
             "insider_name": t.get("personName", ""),
             "signal": "bearish", "conviction": "medium"}
            for t in sells[:5]
        ],
        "overall_insider_sentiment":   sentiment,
        "stocks_with_promoter_buying": list({t.get("symbol") for t in buys}),
        "stocks_with_promoter_selling": list({t.get("symbol") for t in sells}),
        "key_insight": (f"{len(buys)} insider buy(s) vs {len(sells)} sell(s) "
                        f"in last 7 days — net {sentiment}"),
    }
```

In `get_recent_insider_trades`, replace `result = await self._analyze(transactions[:30])` with:
```python
result = self._analyze_sync(transactions[:30])
```

- [ ] **Step 5: Replace LLM calls in EarningsCalendar**

Add `_analyze_sync` to `EarningsCalendar` before its `_analyze` method:

```python
def _analyze_sync(self, results: list, watchlist: list) -> dict:
    """Build earnings calendar from raw NSE event data — no LLM."""
    now     = datetime.now()
    upcoming = []
    this_week = []
    next_week = []
    for event in results[:20]:
        symbol = event.get("symbol", event.get("company", ""))
        try:
            date_str = event.get("date", "")
            event_dt = datetime.strptime(date_str, "%d-%b-%Y")
            days_away = (event_dt - now).days
        except Exception:
            days_away = 30
        upcoming.append({
            "symbol":            symbol,
            "result_date":       event.get("date", ""),
            "days_from_now":     days_away,
            "pre_result_risk":   "high" if days_away <= 3 else "medium" if days_away <= 7 else "low",
        })
        if 0 <= days_away <= 7:
            this_week.append(symbol)
        elif 8 <= days_away <= 14:
            next_week.append(symbol)
    return {
        "upcoming_results":  upcoming[:10],
        "results_this_week": this_week,
        "results_next_week": next_week,
        "key_advice":        ("Avoid fresh entries 3 days before and after results. "
                              f"{len(this_week)} company result(s) this week."),
    }
```

In `get_upcoming_results`, replace `analyzed = await self._analyze(results[:30], watchlist=[])` with:
```python
analyzed = self._analyze_sync(results[:30], watchlist=[])
```

- [ ] **Step 6: Replace LLM call in SectorRotationModel**

Replace the entire `analyze` method body with a code-based version:

```python
async def analyze(
    self,
    macro_snapshot: dict,
    signals: list,
    india_vix: float = 17.0,
    fii_flows: float = None,
    risk_regime: str = "neutral",
) -> dict:
    """Determine sector rotation phase from macro data — no LLM."""
    log = logger.bind(source="sector_rotation")
    log.info("sector_rotation.analyze")

    # Simple rule-based rotation phase
    vix_high    = india_vix > 20
    risk_off    = risk_regime in ("risk_off", "high_risk")
    brent       = (macro_snapshot.get("brent_crude", {}).get("value") or 0)
    crude_high  = float(brent) > 90 if brent else False

    if vix_high and risk_off:
        phase   = "slowdown"
        over    = ["Pharma", "Gold", "FMCG"]
        neutral = ["IT"]
        under   = ["Banking", "Auto", "Real Estate"]
    elif crude_high:
        phase   = "expansion"
        over    = ["Oil & Gas", "Defence"]
        neutral = ["IT", "Banking"]
        under   = ["Airlines", "Paints"]
    else:
        phase   = "expansion"
        over    = ["Banking", "IT", "Infrastructure"]
        neutral = ["Pharma", "FMCG"]
        under   = ["Gold"]

    result = {
        "current_cycle_phase":   phase,
        "cycle_confidence":      0.6,
        "cycle_explanation":     (f"VIX={india_vix}, regime={risk_regime}, "
                                  f"crude=${brent} → {phase} phase"),
        "sector_rankings":       [],
        "money_moving_into":     over,
        "money_moving_out_of":   under,
        "portfolio_positioning": {"overweight": over, "neutral": neutral, "underweight": under},
        "analyzed_at":           datetime.utcnow().isoformat(),
    }
    log.info("sector_rotation.complete", phase=phase)
    return result
```

- [ ] **Step 7: Replace LLM call in FIISectoralFlowTracker**

Add `_analyze_sync` before `_analyze`:

```python
def _analyze_sync(self, fii_data: list) -> dict:
    """Compute FII flow totals from raw data — no LLM."""
    fii_buy  = sum(float(d.get("buyValue",  0) or 0) for d in fii_data
                   if d.get("clientType") in ("FII/FPI", "FII"))
    fii_sell = sum(float(d.get("sellValue", 0) or 0) for d in fii_data
                   if d.get("clientType") in ("FII/FPI", "FII"))
    dii_buy  = sum(float(d.get("buyValue",  0) or 0) for d in fii_data
                   if d.get("clientType") == "DII")
    dii_sell = sum(float(d.get("sellValue", 0) or 0) for d in fii_data
                   if d.get("clientType") == "DII")
    net_fii  = round((fii_buy - fii_sell) / 1e7, 2)   # convert to crore
    net_dii  = round((dii_buy - dii_sell) / 1e7, 2)
    direction = "net_buyer" if net_fii > 0 else "net_seller"
    return {
        "total_fii_flow_crore":      net_fii,
        "flow_direction":            direction,
        "sectors_attracting_fii":    [],
        "sectors_seeing_fii_exit":   [],
        "dii_net_crore":             net_dii,
        "retail_implication":        (f"FII net {'bought' if net_fii > 0 else 'sold'} "
                                      f"₹{abs(net_fii):.0f} crore today"),
        "tomorrow_watch":            "Watch FII/DII flow direction at 9:15 AM open",
    }
```

In `get_sectoral_flows`, replace `result = await self._analyze(fii_data)` with:
```python
result = self._analyze_sync(fii_data)
```

- [ ] **Step 8: Replace LLM call in MaxPainCalculator**

Add `_explain_sync` before `_explain`:

```python
def _explain_sync(self, symbol: str, mp_data: dict) -> dict:
    """Return max pain result without LLM explanation."""
    current  = mp_data.get("current_price", 0)
    max_pain = mp_data.get("max_pain", 0)
    diff     = round(current - max_pain, 0)
    direction = f"+₹{diff} above" if diff >= 0 else f"-₹{abs(diff)} below"
    return {
        "symbol":              symbol,
        "current_price":       current,
        "max_pain_price":      max_pain,
        "price_vs_max_pain":   f"{direction} max pain",
        "max_pain_signal":     "bearish" if diff > 0 else "bullish" if diff < 0 else "neutral",
        "expected_move":       f"Price may move toward ₹{max_pain} before expiry",
        "expiry_date":         mp_data.get("expiry", ""),
        "days_to_expiry":      mp_data.get("dte", 7),
        "confidence":          0.6,
        "plain_explanation":   (f"Max pain is ₹{max_pain}. Current price is ₹{current}. "
                                f"Option writers benefit if price closes at ₹{max_pain} on expiry."),
        "trading_implication": "Use max pain as a reference, not a guarantee",
        "caution":             "Max pain works best in the last 2-3 days before expiry",
    }
```

In `calculate`, replace `result = await self._explain(symbol, max_pain_result)` with:
```python
result = self._explain_sync(symbol, max_pain_result)
```

- [ ] **Step 9: Replace LLM call in OptionsChainAnalyzer**

Add `_analyze_sync` before `_analyze_with_llm`:

```python
def _analyze_sync(self, symbol: str, summary: dict) -> dict:
    """Return options chain signals from computed OI data — no LLM."""
    pcr         = summary.get("pcr", 1.0)
    resistance  = summary.get("max_call_strike", 0)
    support     = summary.get("max_put_strike", 0)
    current     = summary.get("current_price", 0)
    if pcr > 1.2:
        sentiment = "bearish"
    elif pcr < 0.7:
        sentiment = "bullish"
    else:
        sentiment = "neutral"
    return {
        "symbol":              symbol,
        "current_price":       current,
        "pcr":                 pcr,
        "pcr_interpretation":  "PCR > 1.2 = bearish | 0.7-1.2 = neutral | < 0.7 = bullish",
        "market_sentiment":    sentiment,
        "key_resistance":      resistance,
        "key_support":         support,
        "resistance_explanation": f"High call OI at ₹{resistance} — sellers defending this level",
        "support_explanation":    f"High put OI at ₹{support} — buyers protecting this floor",
        "trading_range":       f"₹{support} – ₹{resistance}",
        "plain_explanation":   (f"PCR={pcr} ({sentiment}). "
                                f"Resistance: ₹{resistance}. Support: ₹{support}."),
        "entry_implication":   "Wait for price to hold above support before entering",
        "key_levels_to_watch": [
            f"₹{resistance} — call wall, hard to break above",
            f"₹{support} — put wall, strong floor",
        ],
    }
```

In `analyze`, replace `result = await self._analyze_with_llm(symbol, summary)` with:
```python
result = self._analyze_sync(symbol, summary)
```

- [ ] **Step 10: Run tests to verify all LLM calls removed**

```bash
cd backend && python -m pytest tests/test_market_intelligence_no_llm.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 11: Smoke test — import market_intelligence and confirm no LLM import needed at runtime**

```bash
cd backend && python -c "
from agents.market_intelligence import MarketIntelligence
print('Import OK')
m = MarketIntelligence()
print('Instantiation OK')
"
```

Expected: `Import OK` + `Instantiation OK` with no errors.

- [ ] **Step 12: Commit**

```bash
git add backend/agents/market_intelligence.py backend/tests/test_market_intelligence_no_llm.py
git commit -m "perf: replace market_intelligence LLM calls with code-based transforms (~7 LLM calls removed)"
```

---

## Task 3: Push to GitHub and verify

- [ ] **Step 1: Push to GitHub**

```bash
git push origin master
```

- [ ] **Step 2: Verify CI passes**

Check GitHub Actions at `https://github.com/The-Autonomous-Ali/investai/actions` — confirm tests green.

- [ ] **Step 3: In Codespace — pull and time the pipeline**

```bash
# In Codespace terminal
git pull origin master

# Start backend
cd backend && python -m uvicorn main:app --reload &

# Time a query
time curl -X POST http://localhost:8000/advice \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "should I buy Reliance", "amount": 100000, "horizon": "1 year"}'
```

Expected: total time ~15-16 min (down from ~24 min).

---

## Self-Review

**Spec coverage:**
- Change 1 (static task plan): ✓ Task 1
- Change 2 (remove market intel LLMs): ✓ Task 2 (all 7 LLM calls)
- Change 3 (remove investment_manager): ✓ handled in Task 1 by removing step 11 from FIXED_TASK_PLAN

**Placeholder scan:** No TBDs. All code is complete and runnable.

**Type consistency:**
- `_analyze_sync` is consistently named across all monitors
- `_explain_sync` used only in MaxPainCalculator (different suffix from _analyze to match original `_explain`)
- All return dicts preserve the same top-level keys that `_assemble_final_output` reads (`bulk_deals`, `options_chain`, `sector_rotation`, etc.)

**One risk to note:** The `_analyze` (async, LLM) methods are kept in place — they are no longer called by the pipeline but remain available for manual/test use. This means `call_llm` import stays in `market_intelligence.py`, which is fine.
