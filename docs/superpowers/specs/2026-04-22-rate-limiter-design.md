# Rate Limiter — Design
Date: 2026-04-22
Roadmap link: Phase 1, Item 1 (quota enforcement) — finishes the missing rate-limit piece.

## Goal
Add per-user and per-IP rate limiting to `/api/agents/advice` to
catch runaway clients and unauthenticated abuse. Monthly quota
(already shipped in commit c28a3ec) handles billing; rate limiting
handles short-window abuse.

## Scope
- In: sliding-window rate limiter, wired to the advice endpoint.
- Out: payment enforcement, auth rework, mock fallbacks, other endpoints.

## Design

### Algorithm
Redis sliding window via sorted sets.
- Key: `ratelimit:user:{user_id}` or `ratelimit:ip:{ip}`
- Score = timestamp (seconds, float)
- On each request:
  1. `ZREMRANGEBYSCORE key 0 (now - window)` — evict old
  2. `ZCARD key` — current count
  3. If count >= limit → reject
  4. Else `ZADD key now now` + `EXPIRE key window`

### Limits (defaults, env-overridable)
- `RATE_LIMIT_USER_PER_MIN` = 10
- `RATE_LIMIT_IP_PER_MIN` = 30
- Window = 60 seconds.

### Request pipeline order
1. IP rate-limit check (before auth — protects login-adjacent abuse paths too; here: just advice)
2. Auth (`get_current_user`)
3. User rate-limit check
4. Monthly quota (`ensure_advice_quota`)
5. Pipeline runs
6. `consume_advice_quota` on success

### Rejection response
`HTTPException(429, headers={"Retry-After": "<seconds>"})` with JSON
detail `{ "message": "Rate limit exceeded", "scope": "user|ip",
"retry_after_seconds": N }`.

### Fail-open on Redis error
If Redis is down, log a warning and allow the request. Reason: we'd
rather serve a real user than block everyone during an infra blip.
Monthly quota still applies as the hard ceiling.

## Files
- `backend/services/rate_limiter.py` — new. Async `check_rate_limit(redis, key, limit, window)`.
- `backend/tests/test_rate_limiter.py` — new. AsyncMock-based tests (matches existing patterns).
- `backend/routes/agents.py` — wire limiter before `ensure_advice_quota`.

## Testing
- Allows N requests within the window.
- Rejects (N+1)th request with 429 + Retry-After.
- Old entries evicted correctly (simulated time passage).
- Fail-open when Redis raises.

## Out of scope / follow-ups
- Distributed rate-limit on login/signup routes.
- Per-endpoint limits beyond advice.
- Admin override / allowlist.
