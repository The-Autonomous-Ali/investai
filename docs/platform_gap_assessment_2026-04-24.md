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
| Payment / subscription upgrade | ~~Dev-mode upgrading still possible. No webhook-verified flow.~~ — **DONE 2026-04-26 Day 4.** Razorpay webhook now HMAC-SHA256 verified; subscription.activated/cancelled drives tier; payment.failed audit-only; dev bypass requires explicit ALLOW_DEV_SUBSCRIPTION_BYPASS=true. | #2 ✓ |
| Auth (architecture) | ~~Dual source: NextAuth session + long-lived JWT in localStorage.~~ — **DONE 2026-04-26 Day 2.** JWT now in httpOnly Secure SameSite=strict cookie; localStorage token storage removed; logout endpoint added; legacy Bearer header still honoured during migration. | #3 ✓ |
| WhatIf scenarios | Mock. | (out of roadmap) |
| China data (C4) | Not integrated. | (deferred) |
| NSDL FPI scraper | Mentioned, not implemented. | (deferred) |
| Agent failure surfacing | ~~Silent failures~~ — **DONE 2026-04-26 Day 3.** Orchestrator returns `degraded_components`; `/advice` shows orange warning banner; `call_llm_structured` now retries with exponential backoff (3x), repairs JSON (markdown fences/trailing commas/leading prose), falls back to OpenRouter on persistent failure, and orchestrator gracefully degrades to empty task plan. | #5 ✓ |
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

### 3.3 Silent agent failures (severity: HIGH) — **CLOSED 2026-04-26**
- **What exists:** Agent errors logged + `degraded_components` surfaced to user via orange banner on `/advice`.
- **What's now in place:** `call_llm_structured` validates every LLM response against Pydantic schemas, retries 3x with exponential backoff (2s/4s/8s), repairs JSON (strips markdown fences, leading prose, trailing commas), and falls back to a secondary provider on persistent failure. Orchestrator falls back to an empty task plan instead of crashing on malformed JSON.
- **What's still missing:** Circuit breaker pattern on provider-level (open after N consecutive failures and bypass for cooldown).
- **Roadmap:** #5 ✓

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
2. [x] **Payment enforcement** *(done — 2026-04-26 Day 4)* — Razorpay webhook signature verified, dev bypass requires explicit env
3. [x] **Auth simplification** *(done — 2026-04-26 Day 2)* — httpOnly cookie session, localStorage token storage removed
4. [x] **Kill silent mock fallbacks** *(done — 2026-04-24 Day 1)* — `/dashboard` mock killed
5. [ ] Remove unfinished nav/pages from product surface
6. [x] **LLM schema hardening** *(done — 2026-04-26 Day 3)* — `call_llm_structured` with retry, repair, provider fallback
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

### Day 2 — Auth simplification — DONE (2026-04-26)
- [x] `backend/utils/auth.py` reads JWT from `investai_session` httpOnly cookie. Legacy `Authorization: Bearer` header still honoured during migration.
- [x] `backend/routes/auth.py` `/login` sets cookie (httpOnly + Secure + SameSite=strict + 30-day max-age); `/logout` clears it.
- [x] `frontend/lib/api.js` removed localStorage token, set `withCredentials: true`. Added `logout()` helper.
- [x] `frontend/pages/onboarding.js` and `frontend/pages/invest.js` no longer touch `investai_token`; on 401 they call `loginWithGoogle(idToken)` to seed the cookie.
- [x] Tests: `tests/test_auth_cookie.py` (5 tests, all pass).

### Day 3 — LLM schema hardening — DONE (2026-04-26)
- [x] `backend/utils/llm_schema.py` — `repair_json` (markdown fences, leading prose, trailing commas) + `parse_and_validate` (Pydantic validation).
- [x] `backend/utils/llm_client.py` — `call_llm_structured` with 3-retry exponential backoff (2s/4s/8s) and OpenRouter fallback on persistent failure.
- [x] `backend/agents/orchestrator.py` — `_build_task_plan` uses structured call, falls back to empty plan on persistent failure.
- [x] Tests: `tests/test_llm_schema.py` (9), `tests/test_llm_structured.py` (5), all pass.

### Day 4 — Payment enforcement — DONE (2026-04-26)
- [x] `backend/routes/subscriptions.py` — `_verify_razorpay_signature` (HMAC-SHA256, constant-time compare). Webhook rejects unsigned/missing-secret/tampered requests.
- [x] `subscription.activated` → upgrade user tier from plan_id mapping, set period window, reset query counter.
- [x] `subscription.cancelled` → mark cancelled, downgrade user to FREE.
- [x] `payment.failed`/`payment.captured` → audit log only.
- [x] Dev-mode `/create` bypass requires explicit `ALLOW_DEV_SUBSCRIPTION_BYPASS=true`; otherwise returns 501.
- [x] Tests: `tests/test_subscriptions_webhook.py` (16, all pass).

### Day 5 — Soft-launch invite gate — DONE (2026-04-26)
- [x] `BETA_INVITE_ONLY=true` env activates invite-code requirement in `/api/auth/login`.
- [x] Valid codes (case-insensitive, whitespace-tolerant): `early2026`, `investai-beta`.
- [x] Frontend `signin.js` shows invite-code field when `NEXT_PUBLIC_BETA_INVITE_ONLY=true`; code shuttled via `sessionStorage` through OAuth roundtrip into the `/login` POST.
- [x] Tests: `tests/test_invite_gate.py` (16, all pass).

### Day 5-6 — E2E smoke + buffer — PENDING (next session)
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
