#!/usr/bin/env python
"""
Backend smoke test — exercises every authenticated endpoint without a browser.

Usage:
    cd backend
    python scripts/smoke_test.py                   # hits http://localhost:8000
    BASE_URL=https://my-codespace-8000.app.github.dev python scripts/smoke_test.py
    BASE_URL=... python scripts/smoke_test.py --webhook   # also fires a signed
                                                          # Razorpay webhook event

What it verifies (each prints PASS/FAIL/SKIP):
  1. /health                              — process alive
  2. /health/ready                        — DB + Redis reachable
  3. /api/auth/me without cookie          — 401 (cookie auth gate works)
  4. /api/auth/me with synthetic cookie   — 200 if demo_user seeded, else SKIP
  5. /api/signals/                        — list endpoint reachable
  6. /api/signals/active                  — active signals reachable
  7. /api/subscriptions/plans             — public plan listing
  8. /api/subscriptions/current (auth)    — current tier read
  9. /api/subscriptions/create  (auth)    — must return 501 in prod-mode
 10. /api/agents/advice (auth)            — full pipeline (long-running)
 11. /api/subscriptions/webhook/razorpay  — only with --webhook; verifies that
                                             a SIGNED activation payload is
                                             accepted, an UNSIGNED one is 400.

Synthetic auth: we mint a JWT with the demo_user id directly using SECRET_KEY,
the same key the backend uses. This bypasses the Google OAuth roundtrip so the
script can run unattended in CI / Codespace.

Exit code: 0 if all non-skipped checks pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import jwt

DEFAULT_BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-secret-change-in-prod")
DEMO_USER_ID = os.getenv("SMOKE_DEMO_USER_ID", "demo_user")
DEMO_EMAIL = os.getenv("SMOKE_DEMO_EMAIL", "demo@investai.local")
RAZORPAY_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"


def _mint_session_token() -> str:
    payload = {
        "sub": DEMO_USER_ID,
        "email": DEMO_EMAIL,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.skipped: list[tuple[str, str]] = []

    def record(self, name: str, status: str, detail: str = "") -> None:
        if status == "PASS":
            self.passed.append(name)
            print(f"  {PASS}  {name}")
        elif status == "SKIP":
            self.skipped.append((name, detail))
            print(f"  {SKIP}  {name}  ({detail})")
        else:
            self.failed.append((name, detail))
            print(f"  {FAIL}  {name}  --> {detail}")

    def summary(self) -> bool:
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        print()
        print(f"Summary: {len(self.passed)}/{total} passed, "
              f"{len(self.failed)} failed, {len(self.skipped)} skipped")
        if self.failed:
            print("\nFailures:")
            for name, detail in self.failed:
                print(f"  - {name}: {detail}")
        return not self.failed


def _check(label: str, predicate: bool, detail: str = "") -> tuple[str, str]:
    return ("PASS" if predicate else "FAIL", detail or label)


def smoke(base_url: str, run_webhook: bool) -> bool:
    print(f"InvestAI smoke test against {base_url}\n")
    r = Result()
    token = _mint_session_token()
    cookies = {"investai_session": token}

    with httpx.Client(base_url=base_url, timeout=60.0, follow_redirects=False) as client:

        # ── 1. liveness
        try:
            resp = client.get("/health")
            status, detail = _check("/health 200", resp.status_code == 200,
                                    f"status={resp.status_code}")
            r.record("health", status, detail)
        except Exception as e:
            r.record("health", "FAIL", str(e))

        # ── 2. readiness
        try:
            resp = client.get("/health/ready")
            ok = resp.status_code in (200, 503)
            body = resp.json()
            r.record(
                "health/ready",
                "PASS" if ok and body.get("status") in ("ready", "degraded") else "FAIL",
                f"status={resp.status_code} body={json.dumps(body)[:200]}",
            )
            for name, info in body.get("components", {}).items():
                comp_ok = info.get("ok") is True
                r.record(
                    f"  ↳ {name}",
                    "PASS" if comp_ok else "FAIL",
                    f"{info.get('latency_ms')}ms err={info.get('error')}",
                )
        except Exception as e:
            r.record("health/ready", "FAIL", str(e))

        # ── 3. /me without cookie should be 401
        try:
            resp = client.get("/api/auth/me")
            r.record(
                "auth/me without cookie -> 401",
                "PASS" if resp.status_code == 401 else "FAIL",
                f"got {resp.status_code}",
            )
        except Exception as e:
            r.record("auth/me without cookie", "FAIL", str(e))

        # ── 4. /me with synthetic cookie
        try:
            resp = client.get("/api/auth/me", cookies=cookies)
            if resp.status_code == 200:
                body = resp.json()
                r.record(
                    "auth/me with cookie -> 200",
                    "PASS" if body.get("id") == DEMO_USER_ID else "FAIL",
                    f"id={body.get('id')}",
                )
            elif resp.status_code == 401:
                r.record(
                    "auth/me with cookie",
                    "SKIP",
                    f"demo_user '{DEMO_USER_ID}' not in DB — set SMOKE_DEMO_USER_ID or seed it",
                )
            else:
                r.record("auth/me with cookie", "FAIL", f"status={resp.status_code}")
        except Exception as e:
            r.record("auth/me with cookie", "FAIL", str(e))

        # ── 5. signals list
        try:
            resp = client.get("/api/signals/")
            ok = resp.status_code == 200 and isinstance(resp.json(), (list, dict))
            r.record("signals list", "PASS" if ok else "FAIL", f"status={resp.status_code}")
        except Exception as e:
            r.record("signals list", "FAIL", str(e))

        # ── 6. active signals
        try:
            resp = client.get("/api/signals/active")
            r.record(
                "signals/active",
                "PASS" if resp.status_code == 200 else "FAIL",
                f"status={resp.status_code}",
            )
        except Exception as e:
            r.record("signals/active", "FAIL", str(e))

        # ── 7. plans (public)
        try:
            resp = client.get("/api/subscriptions/plans")
            body = resp.json()
            tiers = [p["tier"] for p in body.get("plans", [])]
            ok = resp.status_code == 200 and {"free", "starter", "pro", "elite"}.issubset(set(tiers))
            r.record("subscriptions/plans", "PASS" if ok else "FAIL",
                     f"status={resp.status_code} tiers={tiers}")
        except Exception as e:
            r.record("subscriptions/plans", "FAIL", str(e))

        # ── 8. current subscription (auth)
        try:
            resp = client.get("/api/subscriptions/current", cookies=cookies)
            if resp.status_code == 200:
                r.record("subscriptions/current", "PASS",
                         f"tier={resp.json().get('tier')}")
            elif resp.status_code == 401:
                r.record("subscriptions/current", "SKIP", "demo_user not in DB")
            else:
                r.record("subscriptions/current", "FAIL",
                         f"status={resp.status_code} body={resp.text[:120]}")
        except Exception as e:
            r.record("subscriptions/current", "FAIL", str(e))

        # ── 9. /create — must be locked unless ALLOW_DEV_SUBSCRIPTION_BYPASS
        try:
            resp = client.post(
                "/api/subscriptions/create",
                cookies=cookies,
                json={"tier": "starter"},
            )
            if resp.status_code == 401:
                r.record("subscriptions/create lockdown", "SKIP", "demo_user not in DB")
            elif resp.status_code == 501:
                r.record("subscriptions/create lockdown", "PASS",
                         "501 as expected (dev bypass off)")
            elif resp.status_code == 200:
                r.record(
                    "subscriptions/create lockdown",
                    "FAIL",
                    "200 returned — dev bypass appears enabled in this env",
                )
            else:
                r.record("subscriptions/create lockdown", "FAIL",
                         f"unexpected status {resp.status_code}")
        except Exception as e:
            r.record("subscriptions/create lockdown", "FAIL", str(e))

        # ── 10. advice — full pipeline (long, may be slow)
        if os.getenv("SMOKE_RUN_ADVICE", "").lower() in {"1", "true", "yes"}:
            try:
                resp = client.post(
                    "/api/agents/advice",
                    cookies=cookies,
                    json={
                        "query": "Should I buy HDFC Bank?",
                        "amount": 50000,
                        "horizon": 12,
                        "country": "IN",
                    },
                    timeout=180.0,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    has_meta = "meta" in body or "policy_version" in body
                    r.record(
                        "agents/advice end-to-end",
                        "PASS" if has_meta else "FAIL",
                        f"keys={list(body.keys())[:6]}",
                    )
                elif resp.status_code in (401, 429):
                    r.record(
                        "agents/advice end-to-end",
                        "SKIP",
                        f"status={resp.status_code} (auth/quota)",
                    )
                else:
                    r.record("agents/advice end-to-end", "FAIL",
                             f"status={resp.status_code} body={resp.text[:200]}")
            except Exception as e:
                r.record("agents/advice end-to-end", "FAIL", str(e))
        else:
            r.record("agents/advice end-to-end", "SKIP",
                     "set SMOKE_RUN_ADVICE=1 to exercise the full pipeline")

        # ── 11. webhook (only when --webhook)
        if run_webhook:
            if not RAZORPAY_SECRET:
                r.record("webhook signed payload", "SKIP",
                         "RAZORPAY_WEBHOOK_SECRET not set")
            else:
                payload = json.dumps({
                    "event": "subscription.activated",
                    "payload": {
                        "subscription": {"entity": {"id": "sub_smoke", "plan_id": "plan_pro_monthly"}},
                        "payment": {"entity": {"email": DEMO_EMAIL}},
                    },
                }).encode()
                sig = hmac.new(RAZORPAY_SECRET.encode(), payload, hashlib.sha256).hexdigest()

                try:
                    resp = client.post(
                        "/api/subscriptions/webhook/razorpay",
                        content=payload,
                        headers={"X-Razorpay-Signature": sig, "content-type": "application/json"},
                    )
                    r.record("webhook signed -> 200", "PASS" if resp.status_code == 200 else "FAIL",
                             f"status={resp.status_code}")

                    resp_bad = client.post(
                        "/api/subscriptions/webhook/razorpay",
                        content=payload,
                        headers={"X-Razorpay-Signature": "deadbeef", "content-type": "application/json"},
                    )
                    r.record("webhook unsigned -> 400", "PASS" if resp_bad.status_code == 400 else "FAIL",
                             f"status={resp_bad.status_code}")
                except Exception as e:
                    r.record("webhook", "FAIL", str(e))

    return r.summary()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--webhook", action="store_true",
                        help="Also fire a signed Razorpay webhook event "
                             "(requires RAZORPAY_WEBHOOK_SECRET).")
    args = parser.parse_args()

    started = time.perf_counter()
    ok = smoke(args.base_url, args.webhook)
    elapsed = time.perf_counter() - started
    print(f"\nElapsed: {elapsed:.1f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
