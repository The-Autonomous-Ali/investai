# Launch Sprint Design — Option A

**Date:** 2026-04-25
**Goal:** Ship private beta on April 30 by completing Days 2-6 of the launch sprint.
**Current state:** Day 1 complete (mock kill, beta banner, degraded surfacing).

---

## Day 2 — Auth Simplification

**Problem:** Dual auth layers (NextAuth session + backend JWT in localStorage). XSS risk, state drift, harder debugging.

**Target state:**
- Backend issues JWT in `httpOnly`, `Secure`, `SameSite=strict` cookie.
- Frontend `lib/api.js` stops reading from `localStorage`; axios uses cookie automatically.
- Remove localStorage JWT storage from auth flow.
- Keep NextAuth for Google OAuth only; backend session becomes the single source of truth for API calls.

**Key files:**
- `backend/routes/auth.py` — set cookie on login, clear cookie on logout
- `frontend/lib/api.js` — remove manual `Authorization` header construction from localStorage
- `frontend/pages/onboarding.js` — remove localStorage JWT storage
- `backend/utils/auth.py` — read JWT from cookie instead of Authorization header

---

## Day 3 — LLM Schema Hardening

**Problem:** `json.loads()` on raw model output is brittle. Malformed JSON breaks runtime.

**Target state:**
- Every LLM call goes through `utils/llm_client.py` with Pydantic schema validation.
- Retry loop: up to 3 attempts with exponential backoff.
- Repair parser: if JSON is malformed, attempt common fixes (strip markdown fences, fix trailing commas) before failing.
- Fallback provider: if Groq fails after retries, switch to OpenRouter; if both fail, return a graceful degradation signal.
- Telemetry: log every validation failure, retry, and fallback with request context.

**Key files:**
- `backend/utils/llm_client.py` — add validation, retry, repair, fallback
- `backend/agents/orchestrator.py` — handle degraded agent output gracefully
- `backend/services/recommendation_policy.py` — ensure policy still builds even if some agent outputs are missing

---

## Day 4 — Payment Enforcement

**Problem:** Dev-mode self-upgrade still possible. No webhook verification.

**Target state:**
- Remove dev-mode bypass from subscription creation.
- Razorpay webhook endpoint verifies signature using `razorpay_secret`.
- Tier activation only happens after verified `subscription.activated` or `payment.captured` event.
- Downgrade/cancellation: webhook handles `subscription.cancelled` by resetting tier to `free` at period end.
- Quota enforcement already works; payment enforcement makes it real.

**Key files:**
- `backend/routes/subscriptions.py` — remove dev bypass, add webhook handler
- `backend/services/entitlements.py` — ensure tier changes from webhooks are respected immediately

---

## Day 5-6 — E2E Smoke Test + Soft Launch

**Goal:** Verify the full user journey works end-to-end.

**Test path:**
1. Google sign-in → onboarding → `/invest`
2. Advice request with quota enforcement
3. Signal page loads real data
4. Alert lifecycle (thesis monitoring) creates and updates alerts
5. Payment flow creates subscription and updates tier

**Soft-launch gate:**
- Add an env var `BETA_INVITE_ONLY=true` that blocks signups without an invite code.
- On Day 7, set to `false` for open private beta.

**Key files:**
- `backend/routes/auth.py` — add invite code check if env var is set
- `frontend/pages/auth/signin.js` — show invite code input when needed

---

## Success Criteria

- [ ] Auth uses httpOnly cookie, no localStorage JWT
- [ ] LLM boundaries validate schema and retry on failure
- [ ] Payment webhooks verify signatures and drive tier changes
- [ ] E2E smoke test passes
- [ ] Platform can accept private beta users on Apr 30

---

## Out of Scope

- Rebuilding `/dashboard` on real data
- Observability stack (metrics, tracing)
- Alembic migrations
- Secrets vault
- Feature flags
- Load testing

These are enterprise-grade gaps for post-beta work.
