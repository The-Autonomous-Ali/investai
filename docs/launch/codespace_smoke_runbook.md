# Codespace Smoke Runbook — Day 5-6

**For:** Sameer, in your GitHub Codespace.
**When to run:** after pulling the launch-sprint commits (auth cookie, LLM hardening, Razorpay webhook, invite gate).
**Goal:** in ~30 minutes, confirm every part of the platform works end-to-end before opening private beta on Apr 30.

There are **two layers** of testing:

1. **Automated** (one command) — script checks every API endpoint without a browser.
2. **Manual** (browser) — the parts a script can't cover: Google sign-in, real `/advice` page, alerts UI.

Run them in order.

---

## Step 0 — Pull the latest code

In your Codespace terminal:

```bash
git pull origin master
```

You should see the 4 new commits:
- `61229cb` feat(auth): httpOnly cookie session + soft-launch invite gate
- `8034e2e` feat(llm): schema validation, retry, repair, fallback
- `75ca1e3` feat(payments): Razorpay webhook signature verification
- `031093f` docs(gap): mark Day 2/3/4/5 launch sprint items complete

Plus this runbook commit (added today).

---

## Step 1 — Set the new env vars

The Razorpay webhook now **fails closed** without a secret. Add this to your `backend/.env` (or Codespace secret):

```bash
# Required for webhook to accept any event (use any random string for the smoke test)
RAZORPAY_WEBHOOK_SECRET=smoke_test_secret_change_in_prod

# Recommended for local http (no HTTPS) — without this, browsers drop the Secure cookie
INSECURE_COOKIES=true

# Optional — flip to true ONLY when you want to test the invite gate
# BETA_INVITE_ONLY=true
# NEXT_PUBLIC_BETA_INVITE_ONLY=true   # this one goes in frontend/.env.local
```

Then restart the backend so it picks up the new vars.

---

## Step 2 — Start backend + frontend

If you don't already have a Codespace dev script, run them in two terminals:

**Terminal A (backend):**
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Wait until you see `✅ All systems ready`.

**Terminal B (frontend):**
```bash
cd frontend
npm run dev
```

Wait until you see `ready - started server on 0.0.0.0:3000`.

---

## Step 3 — Run the automated smoke test

In a **third terminal**:

```bash
cd backend
python scripts/smoke_test.py
```

You should see something like:

```
InvestAI smoke test against http://localhost:8000

  PASS  health
  PASS  health/ready
  PASS    ↳ postgres
  PASS    ↳ redis
  PASS  auth/me without cookie -> 401
  PASS  auth/me with cookie -> 200
  PASS  signals list
  PASS  signals/active
  PASS  subscriptions/plans
  PASS  subscriptions/current
  PASS  subscriptions/create lockdown
  SKIP  agents/advice end-to-end  (set SMOKE_RUN_ADVICE=1 to exercise the full pipeline)

Summary: 11/12 passed, 0 failed, 1 skipped
```

**If any check FAILs, stop and tell me the failure line — don't proceed.** Common causes:
- `health/ready postgres FAIL` → `DATABASE_URL` not set or DB not reachable
- `health/ready redis FAIL` → `REDIS_URL` not set or Redis container not started
- `auth/me with cookie SKIP "demo_user not in DB"` → DB was wiped; restart backend so `ensure_demo_user` re-seeds it
- `subscriptions/create lockdown FAIL "200 returned"` → you have `ALLOW_DEV_SUBSCRIPTION_BYPASS=true` in `.env`; remove it for prod-mode test

### Step 3a — Test the webhook

```bash
python scripts/smoke_test.py --webhook
```

Two new lines should pass:
```
  PASS  webhook signed -> 200
  PASS  webhook unsigned -> 400
```

### Step 3b — (Optional, slow) Test the full advice pipeline

```bash
SMOKE_RUN_ADVICE=1 python scripts/smoke_test.py
```

This actually calls `/api/agents/advice` — takes 30-90 seconds because it runs the whole multi-agent pipeline. PASS means the entire backend chain (auth → orchestrator → agents → policy) works.

---

## Step 4 — Manual browser checklist

Open the Codespace forwarded URL for port 3000 (Codespace shows it in the Ports panel).

| # | What to do | What you should see | If broken |
|---|---|---|---|
| 1 | Visit `/auth/signin` in incognito | Sign-in page, "Continue with Google" button. **No invite field unless you set BETA_INVITE_ONLY.** | If invite field unexpectedly shows, `NEXT_PUBLIC_BETA_INVITE_ONLY=true` is set somewhere |
| 2 | Click "Continue with Google", complete OAuth | Lands on `/onboarding`, "Welcome to InvestAI" with your Google name pre-filled | If 401 redirect loop → cookie not being set; check `INSECURE_COOKIES=true` is set |
| 3 | Enter your name → "Create Account" | Redirects to `/invest` | If error banner "Failed to connect your account" → backend `/api/auth/login` failed; check Terminal A logs |
| 4 | On `/invest`, click "Get AI Advice" or visit `/advice` | Form loads with country/horizon defaults | — |
| 5 | Submit query: "Should I buy HDFC Bank?", amount 50000, horizon 12 | After 30-90s, see action card with confidence %, "Recommended Moves", "Invalidation Triggers", "Known Limits" sections | If just "advice failed" → check Terminal A for which agent died |
| 6 | Look for orange banner above advice | Should appear ONLY if some agent failed (degraded). Lists which components were unavailable. | If it shows up unexpectedly → an agent is silently failing — report it |
| 7 | Visit `/signals` | Real signals list with FRED/RSS feed items | If empty → ingestion not running; check the scheduler logs |
| 8 | Visit `/dashboard` | Should show "Coming Soon" → auto-redirect to `/invest` | If shows old mock data → did you actually pull? |
| 9 | DevTools → Application → Cookies → `localhost:3000` | Should see `investai_session` cookie marked HttpOnly. **NO `investai_token` in localStorage.** | If `investai_token` exists in localStorage → frontend cache is stale; hard reload |
| 10 | DevTools → Application → Local Storage → `localhost:3000` | Empty (or only `investai_user_name`) | Same as #9 |
| 11 | Click profile/menu → "Logout" (if exists) OR call `POST /api/auth/logout` from devtools | `investai_session` cookie disappears, redirected to signin | If cookie persists → logout endpoint not wired |

---

## Step 5 — Test the invite gate (only if launching as invite-only)

This is **optional** — only do it if you actually want to gate beta signups. The plan calls for "private beta" so this is recommended.

**5a.** Add to `backend/.env`:
```bash
BETA_INVITE_ONLY=true
```

**5b.** Add to `frontend/.env.local`:
```bash
NEXT_PUBLIC_BETA_INVITE_ONLY=true
```

**5c.** Restart both backend and frontend.

**5d.** In incognito, visit `/auth/signin` again. You should now see an "Beta Invite Code" input above the sign-in buttons.

**5e.** Try signing in with NO code → expect a 403 from `/api/auth/login` and an error banner on `/onboarding`.

**5f.** Sign in again with code `early2026` → should succeed.

**Valid codes (case-insensitive, whitespace-tolerant):** `early2026`, `investai-beta`. Edit `VALID_INVITE_CODES` in `backend/routes/auth.py` to add more.

---

## Step 6 — Razorpay sandbox smoke (only if you have a Razorpay account)

If you don't have a Razorpay sandbox set up yet, **skip this step** — the offline webhook test in Step 3a is enough to prove our signature verification is correct. Real activation will be tested when you onboard your first paying user.

If you DO have a sandbox:
1. Set `RAZORPAY_WEBHOOK_SECRET` to your real sandbox webhook secret.
2. In Razorpay dashboard → Webhooks → add `https://<codespace-public-url>/api/subscriptions/webhook/razorpay`.
3. Trigger a test `subscription.activated` event from the Razorpay dashboard.
4. Watch Terminal A for `razorpay.subscription_activated` log line.
5. Visit `/api/subscriptions/current` (signed in) — tier should now be `pro` (or whatever the plan_id maps to).

---

## What to report back

After running through this, send me:
1. **Step 3 output** (paste the smoke test summary)
2. **Any FAIL lines** with their detail
3. **Which manual steps (1-11) passed and which broke**
4. **Step 5 result** if you tested invite gate
5. **Step 6 result** if you tested real Razorpay

Once everything is green, we move to the actual private beta launch on Apr 30:
- Drop the `INSECURE_COOKIES` flag (production has HTTPS)
- Set `BETA_INVITE_ONLY=true` permanently
- Set production `RAZORPAY_WEBHOOK_SECRET` from Razorpay dashboard
- Hand out invite codes to your first 10-50 users

---

## Known caveats (don't be alarmed)

- **`test_events_loader.py` fails on Windows** (hardcoded `/tmp` path). Pre-existing, unrelated to launch sprint, doesn't affect runtime. Will fix when convenient.
- **First `/advice` request after a cold start is slow (60-90s)** — agents are loading models + fetching live data. Subsequent requests inside the same session are faster.
- **If Groq is rate-limited**, the LLM client now auto-falls-back to OpenRouter. You'll see a `groq.rate_limit_hit_falling_back_to_openrouter` log line — that's **good**, not a bug.

## Model switch (2026-04-26)

Default LLM is now **Kimi K2** instead of Llama 3.3 70B:
- **Groq:** `moonshotai/kimi-k2-instruct` (same `GROQ_API_KEY`, no new account)
- **OpenRouter fallback:** `moonshotai/kimi-k2:free` (same `OPENROUTER_API_KEY`)

Per-deploy override: set `GROQ_MODEL` or `OPENROUTER_MODEL` env to switch back to Llama (or any other Groq/OpenRouter model) without code changes.

If you see `model_not_found` errors in Terminal A logs, your Groq account may not have Kimi K2 enabled yet — either request access in the Groq console, or set `GROQ_MODEL=llama-3.3-70b-versatile` in `backend/.env` to revert.
