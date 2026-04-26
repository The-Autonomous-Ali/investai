#!/usr/bin/env python
"""
Preflight — verify every external dependency is reachable with REAL credentials.

This is NOT a smoke test. There are no synthetic JWTs, no stubbed payloads.
Every check makes a real network call to a real service using the real keys
in your environment. If preflight passes, the real user journey will work
(barring product bugs). If it fails, fix the env before opening a browser.

Usage:
    cd backend
    python scripts/preflight.py

Exit code: 0 if everything reachable, 1 otherwise.

What it checks:
  1. Postgres   — opens a real connection, runs SELECT 1
  2. Redis      — opens a real connection, runs PING
  3. Groq       — sends a 1-token completion to your default model
  4. OpenRouter — sends a 1-token completion to the fallback model
  5. (optional) Anthropic / Gemini if their keys are present

What it does NOT check:
  - Google OAuth (needs a browser — that's part of the real user test)
  - Razorpay webhook delivery (needs Razorpay sandbox config — separate step)
  - That the LLM produces *good* answers (subjective — you judge in browser)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Awaitable, Callable

import structlog

# Quiet structlog so the script's own output isn't drowned
structlog.configure(processors=[structlog.processors.JSONRenderer()])

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
SKIP = "\033[33m·\033[0m"


class Result:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []
        self.skipped: list[str] = []

    def ok(self, name: str, detail: str = "") -> None:
        print(f"  {PASS} {name}{('  — ' + detail) if detail else ''}")

    def fail(self, name: str, error: str) -> None:
        print(f"  {FAIL} {name}  — {error}")
        self.failures.append((name, error))

    def skip(self, name: str, reason: str) -> None:
        print(f"  {SKIP} {name}  — skipped ({reason})")
        self.skipped.append(name)


async def _timed(label: str, r: Result, fn: Callable[[], Awaitable[str]]) -> None:
    start = time.perf_counter()
    try:
        detail = await fn()
        elapsed = int((time.perf_counter() - start) * 1000)
        r.ok(label, f"{detail} ({elapsed}ms)")
    except Exception as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        r.fail(label, f"{type(e).__name__}: {str(e)[:200]} ({elapsed}ms)")


# ── Real checks ──────────────────────────────────────────────────────────────

async def check_postgres() -> str:
    from sqlalchemy import text
    from database.connection import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT 1 AS one"))
        row = result.first()
        if not row or row[0] != 1:
            raise RuntimeError(f"unexpected row: {row}")
    return "SELECT 1 returned 1"


async def check_redis() -> str:
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    import redis.asyncio as aioredis

    r = aioredis.from_url(url)
    try:
        pong = await r.ping()
    finally:
        await r.aclose()
    if not pong:
        raise RuntimeError("ping returned falsy")
    return f"PING -> PONG ({url})"


async def check_groq() -> str:
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY not set")
    from groq import AsyncGroq

    model = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")
    client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with just OK"}],
        max_tokens=4,
        temperature=0.0,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("empty completion")
    return f"{model} -> {text!r}"


async def check_openrouter() -> str:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY not set")
    from openai import AsyncOpenAI

    model = os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2:free")
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with just OK"}],
        max_tokens=4,
        temperature=0.0,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("empty completion")
    return f"{model} -> {text!r}"


async def check_anthropic() -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    from anthropic import AsyncAnthropic

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = await client.messages.create(
        model=model,
        max_tokens=4,
        messages=[{"role": "user", "content": "Reply with just OK"}],
    )
    text = (resp.content[0].text if resp.content else "").strip()
    if not text:
        raise RuntimeError("empty completion")
    return f"{model} -> {text!r}"


async def check_gemini() -> str:
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY not set")
    import google.generativeai as genai

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(model_name=model_name)
    resp = await model.generate_content_async("Reply with just OK")
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("empty completion")
    return f"{model_name} -> {text!r}"


# ── Runner ───────────────────────────────────────────────────────────────────

async def main() -> int:
    print("InvestAI preflight — real connectivity check\n")
    print("Required:")
    r = Result()

    await _timed("postgres", r, check_postgres)
    await _timed("redis", r, check_redis)
    await _timed("groq (default LLM)", r, check_groq)

    print("\nRecommended:")
    if os.getenv("OPENROUTER_API_KEY"):
        await _timed("openrouter (LLM fallback)", r, check_openrouter)
    else:
        r.skip("openrouter", "OPENROUTER_API_KEY not set — Kimi rate-limit fallback won't work")

    print("\nOptional escape hatches:")
    if os.getenv("ANTHROPIC_API_KEY"):
        await _timed("anthropic", r, check_anthropic)
    else:
        r.skip("anthropic", "ANTHROPIC_API_KEY not set")

    if os.getenv("GOOGLE_API_KEY"):
        await _timed("gemini", r, check_gemini)
    else:
        r.skip("gemini", "GOOGLE_API_KEY not set")

    print()
    if r.failures:
        print(f"\033[31m{len(r.failures)} REQUIRED check(s) failed:\033[0m")
        for name, err in r.failures:
            print(f"  - {name}: {err}")
        print("\nFix the env (.env file or Codespace secrets), then re-run preflight.")
        print("Do NOT open the browser test until preflight is green.")
        return 1

    if r.skipped:
        print(f"\033[33m{len(r.skipped)} optional check(s) skipped — see above.\033[0m")
    print("\033[32m\nAll required checks passed. Real user journey can proceed.\033[0m")
    return 0


if __name__ == "__main__":
    # Load backend/.env so the script picks up local-only secrets, mirroring
    # how main.py boots.
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    except ImportError:
        pass
    sys.exit(asyncio.run(main()))
