# Real Test Plan — Day 5-6

**For:** Sameer, in your Codespace, before opening private beta.
**Length:** ~45 min total (15 min real journey + 20 min failure modes + 10 min Razorpay).
**Philosophy:** No synthetic JWTs. No stubbed payloads. You sign in as a real user, ask a real question, get a real answer. We validate the failure paths with real triggers, not mocks.

If anything fails, **stop and tell me** — don't push through it.

---

## Stage 0 — Pull the latest (1 min)

```bash
git pull origin master
```

Expected new commits (most recent on top):
- `d14db83` feat(llm): switch default model from Llama 3.3 70B to Kimi K2
- `99af94f` feat(day5-6): readiness probe + smoke test + Codespace runbook
- `031093f`, `75ca1e3`, `8034e2e`, `61229cb` (the launch sprint)

---

## Stage 1 — Real environment preflight (1 min)

This is **not** a smoke test. It opens real network connections to Groq, OpenRouter, Postgres, Redis using your real keys. If it fails, the browser test will fail — fix env first.

```bash
cd backend
python scripts/preflight.py
```

Expected output:
```
InvestAI preflight — real connectivity check

Required:
  ✓ postgres  — SELECT 1 returned 1 (12ms)
  ✓ redis  — PING -> PONG (redis://localhost:6379) (4ms)
  ✓ groq (default LLM)  — moonshotai/kimi-k2-instruct -> 'OK' (340ms)

Recommended:
  ✓ openrouter (LLM fallback)  — moonshotai/kimi-k2:free -> 'OK' (820ms)

Optional escape hatches:
  · anthropic  — skipped (ANTHROPIC_API_KEY not set)
  · gemini  — skipped (GOOGLE_API_KEY not set)

All required checks passed. Real user journey can proceed.
```

**Likely failure modes:**
- `groq` fails with `model_not_found` → your Groq account doesn't have Kimi K2 enabled. Either request access in the Groq console, OR set `GROQ_MODEL=llama-3.3-70b-versatile` in `backend/.env` and re-run.
- `redis` fails → Redis container isn't running. In Codespace devcontainer it should auto-start — check `docker ps` (or `redis-cli ping`).
- `postgres` fails → `DATABASE_URL` wrong or DB not initialized. Check `backend/.env`.

**Do NOT proceed to Stage 2 until preflight is fully green.**

---

## Stage 2 — Start backend + frontend (2 min)

In **two separate terminals** in Codespace:

**Terminal A — backend:**
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Wait for `✅ All systems ready`.

**Terminal B — frontend:**
```bash
cd frontend
npm run dev
```
Wait for `ready - started server on 0.0.0.0:3000`.

Open the **forwarded port 3000 URL** that Codespace shows in the Ports panel (the public `*.app.github.dev` URL, not localhost). Tell me the URL — I'll keep it in context.

---

## Stage 3 — Real user journey (15 min, the actual product test)

You're testing as a **real user signing up for the first time**. Use your real Gmail.

### 3.1 — First sign-in (3 min)

| Step | What to do | What to verify |
|---|---|---|
| 1 | Open the Codespace URL in **incognito** window | Landing page renders. No "Beta Invite Code" field (gate is off in this run) |
| 2 | Click "Continue with Google" | Real Google OAuth popup. Sign in with your real account |
| 3 | Returned to `/onboarding` | Your real Google name pre-filled in the form |
| 4 | Open DevTools → Application → Cookies | **`investai_session` cookie exists, marked HttpOnly. NOTHING in localStorage named `investai_token`.** This is the auth-cookie test passing for real. |
| 5 | Type your name, "Create Account" | Redirects to `/invest`. No errors. |

If step 4 shows `investai_token` in localStorage → frontend cache is stale. Hard reload (Ctrl+Shift+R) and try again.

### 3.2 — First real advice query (8 min)

This is the test that matters most. The full multi-agent pipeline runs against real Kimi K2 with real signals.

| Step | What to do | What to verify |
|---|---|---|
| 6 | Click "Get AI Advice" or visit `/advice` | Form loads with horizon/country defaults |
| 7 | Submit: "Should I buy HDFC Bank for a 12-month horizon?" amount 50000, country IN | Loading spinner. Wait. **First request can be 60-90 seconds — agents are warming up + fetching live signals.** |
| 8 | Watch Terminal A logs | You should see lines like `llm_client.call agent=orchestrator provider=groq model=moonshotai/kimi-k2-instruct`, then a cascade of agent calls (signal_watcher, research_agent, etc.) |
| 9 | Response renders | Action card shows BUY/HOLD/SELL with strength (e.g. "BUY — Moderate Conviction"). Confidence percentage visible. "Recommended Moves" list. "Invalidation Triggers" list. "Known Limits" section. |
| 10 | Read the advice quality | **This is the subjective check.** Is the answer specific to HDFC Bank? Does it reference real macro context (rates, NIM, asset quality)? Or is it generic boilerplate? Tell me what you see — paste the advice text into chat |
| 11 | Look for orange degraded banner above advice | If present → some agent failed silently. Note which components are listed. We may need to debug. If absent → all 10+ agents ran clean. Good. |

### 3.3 — Browse and verify side surfaces (4 min)

| Step | What to do | What to verify |
|---|---|---|
| 12 | Visit `/signals` | List of real signals from FRED + RSS feeds. Item titles, dates, sources. Not "no signals available" |
| 13 | Click any signal | Detail page loads with full context, root_cause_chain if present |
| 14 | Visit `/dashboard` | Should see "Coming Soon" page → auto-redirect to `/invest` after 2s. **NOT** old mock data |
| 15 | Visit `/api/auth/me` directly in browser | JSON of your user profile. Tier shows "free", queries_used_this_month should now be 1 (you used one above) |

---

## Stage 4 — Real failure modes (20 min, walk through with me)

### 4.1 — FREE tier quota exhaustion (5 min)

You're on FREE tier (3 queries/month). You used 1 in stage 3. Send 2 more from the `/advice` page. After the 3rd, send a 4th.

Expected:
- Queries 2 & 3: succeed
- Query 4: 429 response with `Quota exhausted` message. Frontend should show an upgrade prompt, not crash.

Tell me what you see on query 4.

### 4.2 — Sliding-window rate limit (3 min)

The advice endpoint has 10/min per-user + 30/min per-IP. We can't hit that in normal browsing. To test: open 11 tabs and submit the same query in each within 60s. (Optional — only do this if you care to verify; the unit tests already cover this and it'll burn your quota.)

### 4.3 — Real Razorpay sandbox webhook (8 min)

This is the only payment test that actually proves the end-to-end works. Skip if you don't have a Razorpay sandbox account yet.

**4.3.a — Set up Razorpay sandbox webhook**
1. Log into https://dashboard.razorpay.com (test mode toggle on top)
2. Settings → Webhooks → Add webhook
3. URL: `https://<your-codespace-public-url>/api/subscriptions/webhook/razorpay`
4. Active events: `subscription.activated`, `subscription.cancelled`, `payment.captured`, `payment.failed`
5. Secret: copy whatever Razorpay generates
6. Add this secret to `backend/.env` as `RAZORPAY_WEBHOOK_SECRET=<the secret>`
7. Restart Terminal A

**4.3.b — Trigger a test event**
1. In Razorpay dashboard → Webhooks → click your webhook → "Send Test Webhook"
2. Pick `subscription.activated`
3. Modify the test payload's `payment.entity.email` to your Gmail (the one you signed in with)

**4.3.c — Verify**
1. Watch Terminal A logs. You should see `razorpay.subscription_activated` log line with your user_id
2. In browser, visit `/api/auth/me` → tier should now be `pro` (or whatever the test plan_id mapped to)
3. Send another `/advice` query — quota should now be unlimited (no 429 even if you send 5 in a row)

If step 1 logs `razorpay.invalid_signature` → the secret in `.env` doesn't match what Razorpay sent. Re-copy.

### 4.4 — Soft-launch invite gate (4 min)

Only do this if you're planning to launch invite-only.

1. Add to `backend/.env`: `BETA_INVITE_ONLY=true`
2. Add to `frontend/.env.local`: `NEXT_PUBLIC_BETA_INVITE_ONLY=true`
3. Restart both terminals
4. Open a **new incognito window** (so you have a fresh session)
5. Try to sign in with no invite code → should fail with "Private beta requires a valid invite code"
6. Try with code `early2026` → should succeed

---

## Stage 5 — What to report back

Send me:

1. **Preflight output** — was anything skipped or failed?
2. **The actual advice text from Stage 3.2** — paste it. I'll judge quality with you.
3. **Anything that broke** — exact error from Terminal A logs, plus what you were doing
4. **Stage 4 results** — quota worked? webhook worked? invite gate worked?
5. **Anything that *felt* off** even if it didn't error — slow page? confusing UI? unclear copy?

If everything is green, **we ship to private beta on Apr 30**. If something is broken, we fix and re-test.

---

## What this test does NOT cover (and that's OK for now)

- **Production HTTPS cookies** — `INSECURE_COOKIES=true` is for Codespace local. Production at `investai.in` uses HTTPS so the Secure flag works automatically.
- **Real Google OAuth client secret rotation** — your current `GOOGLE_CLIENT_ID` is whatever you've been using.
- **Load testing** — explicitly deferred per the launch plan. Beta is 10-50 users; load isn't the bottleneck.
- **Adversarial security testing** — also deferred. This is a friendly-user beta.

---

## The smoke script (`scripts/smoke_test.py`) is still useful — but for a different job

After this real test passes, the smoke script becomes a **CI/regression check** — run it whenever I push code changes to confirm "nothing broke that used to work". It uses synthetic auth precisely because CI can't sign into Google. For pre-launch validation, it's the wrong tool. This real test plan is the right tool.
