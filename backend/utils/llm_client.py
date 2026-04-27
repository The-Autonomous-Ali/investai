"""
Universal LLM Client — Routes each agent to its optimal free model provider.

Model defaults (2026-04-26): switched from Llama 3.3 70B to Kimi K2.
- Groq hosts Kimi K2 as `moonshotai/kimi-k2-instruct` (same GROQ_API_KEY).
- OpenRouter free tier serves it as `moonshotai/kimi-k2:free`.
- Both are drop-in OpenAI-compatible — no SDK changes required.
- Override per-deploy with GROQ_MODEL / OPENROUTER_MODEL env vars.
"""

import asyncio
import json
import os

import structlog
from pydantic import BaseModel, ValidationError

from utils.llm_schema import parse_and_validate

logger = structlog.get_logger()

AGENT_MODELS = {
    # ── Core Pipeline ──────────────────────────────────────────────────────────
    "orchestrator":              {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "signal_watcher":            {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Layer 1 — Global Macro Intelligence ───────────────────────────────────
    "global_macro_agent":        {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Analysis Layer ─────────────────────────────────────────────────────────
    "research_agent":            {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "pattern_matcher":           {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "temporal_agent":            {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Company Layer ──────────────────────────────────────────────────────────
    "company_intelligence":      {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Layer 3 — Sentiment Aggregator ────────────────────────────────────────
    "sentiment_aggregator":      {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Portfolio & Tax ────────────────────────────────────────────────────────
    "portfolio_agent":           {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "tax_agent":                 {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Validation Layer ───────────────────────────────────────────────────────
    "critic_agent":              {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "watchdog":                  {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Output & Feedback ──────────────────────────────────────────────────────
    "investment_manager":        {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "performance_tracker":       {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── What If Simulator ─────────────────────────────────────────────────────
    "whatif_agent":              {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── GraphRAG Enricher ─────────────────────────────────────────────────────
    "graphrag_enricher":         {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Data Scrapers ─────────────────────────────────────────────────────────
    "data_scraper":              {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Technical Analysis (Candlestick + Volatility) ─────────────────────────
    "technical_analysis_agent":  {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},

    # ── Plain Language Formatter ──────────────────────────────────────────────
    "plain_language_formatter":  {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "market_intelligence":       {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
    "free_data_feeds":           {"provider": "groq",       "model": "moonshotai/kimi-k2-instruct"},
}

DEFAULT_MODEL = {"provider": "groq", "model": "moonshotai/kimi-k2-instruct"}

SYSTEM_PROMPT = "You are a financial AI assistant. Always respond with valid JSON only. No markdown, no code fences, no extra text before or after the JSON."

# ── Provider Callers ───────────────────────────────────────────────────────────

async def _call_groq(prompt: str, model_name: str) -> str:
    from groq import AsyncGroq
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        # On Groq rate limit: try OpenRouter if key is set, else retry once after delay
        if "429" in str(e) or "rate_limit" in str(e):
            if os.getenv("OPENROUTER_API_KEY"):
                logger.warning("groq.rate_limit_hit_falling_back_to_openrouter")
                return await _call_openrouter(prompt, os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2:free"))
            logger.warning("groq.rate_limit_hit_retrying", delay_s=8)
            await asyncio.sleep(8)
            response2 = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=4096,
                temperature=0.1,
            )
            return response2.choices[0].message.content
        raise


async def _call_openrouter(prompt: str, model_name: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    return response.choices[0].message.content


async def _call_kaggle(prompt: str, model_name: str) -> str:
    """Call Ollama server running on Kaggle, exposed via ngrok tunnel.

    Uses Ollama's OpenAI-compatible endpoint at `{base}/v1/chat/completions`.
    KAGGLE_LLM_URL is the ngrok https URL (no trailing slash, no /v1).
    """
    from openai import AsyncOpenAI
    base = os.getenv("KAGGLE_LLM_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("KAGGLE_LLM_URL not set")
    client = AsyncOpenAI(
        base_url=f"{base}/v1",
        api_key="ollama",  # Ollama ignores the key but SDK requires a non-empty string
        default_headers={"ngrok-skip-browser-warning": "true"},
        timeout=300.0,     # local GPU inference can be slow on first token
    )
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    return response.choices[0].message.content


async def _call_gemini(prompt: str, model_name: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
    )
    response = await model.generate_content_async(prompt)
    return response.text


async def _call_anthropic(prompt: str, model_name: str) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model=model_name,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Main Entry Point ───────────────────────────────────────────────────────────

async def call_llm(prompt: str, agent_name: str = "default") -> str:
    """
    Route a prompt to the correct provider.

    AI_PROVIDER in .env:
      groq       → all agents use Groq Kimi K2 (default; fast, free, JSON-friendly)
      anthropic  → all agents use Claude (production)
      openrouter → all agents go through OpenRouter Kimi K2 free tier
      gemini     → all agents use Google Gemini
      kaggle     → all agents use Ollama/Gemma on Kaggle via ngrok tunnel
      auto       → each agent uses its designated model from AGENT_MODELS
    """
    global_provider = os.getenv("AI_PROVIDER", "groq")

    if global_provider == "anthropic":
        model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        text = await _call_anthropic(prompt, model_name)
        return _clean(text)

    if global_provider == "groq":
        model_name = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")
        text = await _call_groq(prompt, model_name)
        return _clean(text)

    if global_provider == "openrouter":
        model_name = os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2:free")
        text = await _call_openrouter(prompt, model_name)
        return _clean(text)

    if global_provider == "gemini":
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        text = await _call_gemini(prompt, model_name)
        return _clean(text)

    if global_provider == "kaggle":
        model_name = os.getenv("KAGGLE_LLM_MODEL", "gemma4:26b")
        text = await _call_kaggle(prompt, model_name)
        return _clean(text)

    # Per-agent routing (AI_PROVIDER=auto)
    config   = AGENT_MODELS.get(agent_name, DEFAULT_MODEL)
    provider = config["provider"]
    model    = config["model"]

    log = logger.bind(agent=agent_name, provider=provider, model=model)
    log.info("llm_client.call")

    try:
        if provider == "groq":
            text = await _call_groq(prompt, model)
        elif provider == "openrouter":
            text = await _call_openrouter(prompt, model)
        elif provider == "gemini":
            text = await _call_gemini(prompt, model)
        elif provider == "kaggle":
            text = await _call_kaggle(prompt, model)
        else:
            log.warning("llm_client.unknown_provider", fallback="groq")
            text = await _call_groq(prompt, "moonshotai/kimi-k2-instruct")

        return _clean(text)

    except Exception as e:
        log.error("llm_client.error", error=str(e))
        if provider != "groq":
            log.warning("llm_client.fallback_to_groq")
            try:
                text = await _call_groq(prompt, "moonshotai/kimi-k2-instruct")
                return _clean(text)
            except Exception as fe:
                log.error("llm_client.fallback_failed", error=str(fe))
        raise


def _clean(text: str) -> str:
    if not text:
        return "{}"
    return text.strip().replace("```json", "").replace("```", "").strip()


# ── Schema-validated entry point ───────────────────────────────────────────────

# Provider for last-ditch fallback when the configured provider keeps producing
# malformed output. Set to None to disable.
_FALLBACK_MODEL = "moonshotai/kimi-k2:free"


async def call_llm_structured(
    prompt: str,
    schema: type[BaseModel],
    agent_name: str = "default",
    max_retries: int = 3,
    fallback_provider: str | None = "openrouter",
) -> BaseModel:
    """
    Call the LLM, parse the response as JSON, and validate against ``schema``.

    Strategy:
      1. Try the configured provider up to ``max_retries`` times. Each failure
         backs off exponentially (2s, 4s, 8s) before retrying.
      2. If every retry fails and ``fallback_provider`` differs from the active
         provider, do one last attempt against the fallback.
      3. Raise the most recent error if everything fails.
    """
    log = logger.bind(agent=agent_name, schema=schema.__name__)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            raw = await call_llm(prompt, agent_name)
            return parse_and_validate(raw, schema)
        except (ValidationError, json.JSONDecodeError) as e:
            last_error = e
            log.warning(
                "llm_schema.validation_failed",
                attempt=attempt,
                max_retries=max_retries,
                error=str(e)[:200],
            )
            if attempt < max_retries:
                wait = 2 ** attempt
                log.info("llm_schema.retrying", wait_seconds=wait)
                await asyncio.sleep(wait)
        except Exception as e:
            # Provider-level errors (rate limits, network) — bail out and let
            # the fallback provider take over below.
            last_error = e
            log.warning("llm_schema.provider_error", attempt=attempt, error=str(e)[:200])
            break

    active_provider = os.getenv("AI_PROVIDER", "groq")
    if fallback_provider and fallback_provider != active_provider:
        log.warning("llm_schema.fallback_provider", provider=fallback_provider)
        try:
            if fallback_provider == "openrouter":
                raw = await _call_openrouter(prompt, _FALLBACK_MODEL)
            elif fallback_provider == "groq":
                raw = await _call_groq(prompt, "moonshotai/kimi-k2-instruct")
            elif fallback_provider == "gemini":
                raw = await _call_gemini(prompt, os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
            else:
                raise RuntimeError(f"Unknown fallback provider: {fallback_provider}")
            return parse_and_validate(_clean(raw), schema)
        except Exception as e:
            log.error("llm_schema.fallback_failed", error=str(e)[:200])
            last_error = e

    log.error("llm_schema.all_attempts_failed", error=str(last_error)[:200])
    assert last_error is not None
    raise last_error

