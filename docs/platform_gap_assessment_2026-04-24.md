# InvestAI — Platform Gap Assessment

**Date:** 2026-04-24
**Purpose:** Honest snapshot of what exists, what's stubbed, and what's missing to reach enterprise-grade. Cross-referenced to `recommended_roadmap.txt` so gaps map to the prioritized to-do list.
**How to use this doc:** When a gap closes, move it from the "Missing" column to "Done" with the commit SHA. This is a living file.

**Current readiness estimate:** ~30% to enterprise-ship. Core logic is genuinely good. The scaffolding around it is hobby-grade.

---

## Section 1 — What's real and working

| Subsystem | Status | Detail |
|---|---|---|
| Ingestion connectors | Working | 33 connectors: RSS (RBI, Fed, ECB, BOE, BOJ + ET/Mint/Moneycontrol/Reuters/BBC/NYT/WSJ), FRED macro (rates, CPI, unemployment, VIX), yFinance (indices, commodities, currencies, bonds, crypto, ETFs). |
| Dedup pipeline | Working | 3-layer: in-memory cache (10k per connector) → Redis SET (7-day TTL) → Postgres unique constraint on `content_hash`. |
| Redis stream ingestion | Working | `signals.raw` stream → SignalExtractor consumer → Postgres with LLM enrichment (urgency, sectors, india_impact, claim_type, second_order_effects). |
| Orchestrator pipeline | Working | 10+ specialist agents: signal watcher → global macro → research → pattern matcher → temporal → company intel → adversarial (bull/bear) → sentiment → portfolio → tax → investment manager → critic → plain-language formatter → policy. |
| Recommendation policy | Working | `services/recommendation_policy.py` enforces output contract: action + strength, confidence + basis, recommended_moves[], invalidation_triggers, suitability_checks, review_date, policy_version, known_limits. |
| LLM provider abstraction | Working | Groq (primary) + OpenRouter (rate-limit fallback) + Claude/Gemini/Kaggle selectable via `AI_PROVIDER` env. Temp 0.1, JSON-only system prompt. |
| Advice endpoint | Working | `/api/agents/advice` — JWT-auth, sliding-window rate limits (10/min user, 30/min IP), quota-gated (free 3/mo, starter 30, pro/elite unlimited). |
| `/advice` frontend page | Working | Wired to real backend (commit 638f44a). Shows confidence, moves, invalidation triggers, known limits. |
| `/signals`, `/invest`, `/onboarding`, `/auth/signin` | Working | All real, no mocks. |
| Background worker | Partial | APScheduler: signals scan every 15 min, signal-change monitor every 30 min, continuous extractor loop. |
| Tests + CI | Partial | ~70 test files, 15% coverage gate on `agents/` + `utils/`, GitHub Actions runs pytest + secret scan. |
| Auth (functional) | Working (complex) | NextAuth Google OAuth → `/api/auth/login` → JWT (30-day expiry). Works but dual-source (see Section 3). |

---

## Section 2 — What's stubbed or broken

| Thing | Reality | Roadmap item |
|---|---|---|
| `/dashboard` | ~~Mock data~~ — **KILLED 2026-04-24 Day 1.** Page is now "Coming Soon" + redirect to `/invest` for authed users. Real-data dashboard deferred to post-launch. | #4 ✓, #11 deferred |
| Critic agent | 28 bytes — a placeholder. Should review sanity and catch conflicts. | (out of roadmap) |
| Event lifecycle updater | Logs start/end, does nothing. | #8 |
| Advice performance scoring (30/90/180d) | Marked for scoring, never scored. | #13 |
| Alembic migrations | **Directory is empty.** Schema lives in code only. No rollback. No dev→staging→prod parity. | (infra — not on roadmap yet) |
| Payment / subscription upgrade | Dev-mode upgrading still possible. No webhook-verified flow. | #2 |
| Auth (architecture) | Dual source: NextAuth session + long-lived JWT in localStorage. | #3 |
| WhatIf scenarios | Mock. | (out of roadmap) |
| China data (C4) | Not integrated. | (deferred) |
| NSDL FPI scraper | Mentioned, not implemented. | (deferred) |
| Agent failure surfacing | ~~Silent failures~~ — **PARTIAL FIX 2026-04-24 Day 1.** Orchestrator now returns `degraded_components` list; `/advice` shows orange warning banner naming failed components. Full schema hardening (retry/repair) still pending on Day 3. | #5 partial |
| 24/7 monitoring | 15-min polling, not 24/7 streaming. Extractor loop is continuous, scans are not. | #7, #14 |

---

## Section 3 — Enterprise-grade gaps

Ranked by "what bites you first when you ship".

### 3.1 Observability black hole (severity: HIGH)
- **What exists:** structlog logs.
- **What's missing:** Metrics collection (Prometheus/StatsD), distributed tracing (request path through 10+ agents), Grafana dashboards, alerting on error budgets or background job failures.
- **Impact:** Cannot diagnose why advice is slow or why signals are stale. Every production incident is a blind investigation.
- **Roadmap:** #14

### 3.2 Empty alembic/ migrations (severity: HIGH)
- **What exists:** `alembic.ini` + empty migrations directory. Schema in models.py.
- **What's missing:** Actual migration files, version control, rollback capability.
- **Impact:** Any schema change is a manual prayer. Cannot safely move between dev/staging/prod. Data loss risk on any column change.
- **Roadmap:** Not explicit — add as infra item.

### 3.3 Silent agent failures (severity: HIGH)
- **What exists:** Agent errors logged.
- **What's missing:** No surfacing to user, no circuit breaker on LLM provider failures beyond rate-limit fallback, no graceful degradation (e.g., advice without company picks labeled as such), no exponential backoff.
- **Impact:** Advice looks authoritative even when half the agents errored. Kills trust the moment a user notices.
- **Roadmap:** #5

### 3.4 Secrets management (severity: MEDIUM-HIGH)
- **What exists:** `.env` files, env vars.
- **What's missing:** Vault integration (HashiCorp Vault / AWS Secrets Manager), secret rotation, separate staging/prod configs.
- **Impact:** Key compromise = full system compromise. No safe way to rotate keys.
- **Roadmap:** Not on roadmap — add as infra item.

### 3.5 Audit logging + PII handling (severity: MEDIUM-HIGH, becomes HIGH at scale)
- **What exists:** Queries stored in `advice_records.user_query`.
- **What's missing:** PII masking in logs (emails, user IDs logged with full request context), GDPR right-to-be-forgotten, audit trail of who accessed what advice when.
- **Impact:** Compliance violations, data breach blast radius.
- **Roadmap:** Adjacent to #11.

### 3.6 No staging environment (severity: MEDIUM)
- **What exists:** Dev (local) and prod.
- **What's missing:** Staging with prod-like data, canary deploy strategy, rollback playbook.
- **Impact:** Every deploy is a prod deploy. No safe place to validate changes.
- **Roadmap:** Not explicit.

### 3.7 No feature flags (severity: MEDIUM)
- **What exists:** Hard deploys for every rollout.
- **What's missing:** Feature flag system (even a simple DB-backed one).
- **Impact:** Cannot A/B test, cannot roll out to a cohort, cannot kill a feature without a redeploy.
- **Roadmap:** Not explicit.

### 3.8 Multi-tenancy not ready (severity: LOW now, HIGH if you go B2B)
- **What exists:** Implicit user_id filtering.
- **What's missing:** Database-level RBAC, org/team concept, tier enforcement beyond quota.
- **Impact:** B2B/workspace pivot requires major refactor. Fine for retail-only for now.
- **Roadmap:** Deferred.

### 3.9 No data retention policy (severity: LOW now, MEDIUM at scale)
- **What exists:** Signals stored forever.
- **What's missing:** TTL / archival / cold-storage strategy.
- **Impact:** Storage costs grow unbounded.
- **Roadmap:** Deferred.

### 3.10 No load testing (severity: LOW)
- **What exists:** Functional test suite.
- **What's missing:** k6 / Locust load tests; unknown breaking point.
- **Impact:** First traffic spike could degrade unpredictably.
- **Roadmap:** Deferred.

---

## Section 4 — Recommended priority order (from roadmap)

From `docs/recommended_roadmap.txt`, the practical priority:

1. [x] Quota enforcement *(done — 9618bd4)*
2. [ ] **Payment enforcement** — webhook-verified tier activation, kill dev-mode upgrades
3. [ ] **Auth simplification** — one source of truth, httpOnly cookies, kill localStorage JWT
4. [ ] **Kill silent mock fallbacks** — `/dashboard` is the poster child
5. [ ] Remove unfinished nav/pages from product surface
6. [ ] **LLM schema hardening** — retry/repair/fallback on malformed JSON
7. [ ] Slim synchronous advice path (move to pre-compute)
8. [ ] Ingestion consolidation (pick legacy OR stream, retire the other)
9. [ ] Alert dedupe + lifecycle
10. [ ] Compliance posture decision *(memory says this is locked to Option 1 — re-confirm)*
11. [ ] Rebuild `/dashboard` on real data
12. [ ] Moat features + feedback loops (signal provenance, causal chain UX, thesis health, calibration)

**Infra items not yet on roadmap (candidates to add):**
- Alembic migrations (depends on any future schema change)
- Observability (metrics + tracing + alerting)
- Secrets vault integration
- Staging environment
- Feature flags

---

## Section 5 — Launch sprint progress

**Path chosen:** Scenario A — private beta Apr 30, enterprise public launch late July.
**Last updated:** 2026-04-24.

### Day 1 (2026-04-24) — Kill mocks + Beta banner + degraded surfacing — DONE
- [x] `/dashboard` mock killed — now a "Coming Soon" page that auto-redirects authed users to `/invest`. All `MOCK_SIGNALS`, `MOCK_PORTFOLIO_ALLOCATION`, `MOCK_PORTFOLIO_PERFORMANCE`, `MOCK_ACTIVE_EVENTS` removed.
- [x] `frontend/components/BetaBanner.js` created — shared, site-wide via `_app.js`.
- [x] Nav links from `/advice` and `/signals` re-pointed from `/dashboard` → `/invest` (actual post-login home).
- [x] Backend `orchestrator.py` now computes `degraded_components` list (agents with error in `state["agent_outputs"]`) and returns via `meta`.
- [x] Route `agents.py` copies `degraded_components` onto final recommendation after policy.build.
- [x] Frontend `/advice` renders orange warning banner listing unavailable components (human-readable names via `AGENT_LABELS`) when any agent failed.

### Day 2 (2026-04-25) — Auth simplification — PENDING
### Day 3 (2026-04-26) — LLM schema hardening — PENDING
### Day 4 (2026-04-27) — Payment enforcement — PENDING
### Day 5 (2026-04-28) — E2E smoke + soft launch — PENDING
### Day 6 (2026-04-29) — Fix + buffer — PENDING
### Day 7 (2026-04-30) — Private beta launch — PENDING

---

## Section 6 — Do NOT do next

From the roadmap, explicit anti-priorities:
- ✘ Add more agents
- ✘ Add more charts
- ✘ Add more premium tiers
- ✘ Add prettier marketing pages
- ✘ Add more signal sources before fixing trust and reliability

These are not the bottleneck right now. If you feel pulled toward them, re-read Section 3.
