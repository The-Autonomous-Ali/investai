"""
Universal LLM Client — Routes each agent to its optimal free model provider.
UPDATED: Replaced discontinued qwen model with working free alternatives.
"""

import os
import structlog

logger = structlog.get_logger()

AGENT_MODELS = {
    # ── Core Pipeline ──────────────────────────────────────────────────────────
    "orchestrator":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "signal_watcher":            {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Layer 1 — Global Macro Intelligence ───────────────────────────────────
    "global_macro_agent":        {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Analysis Layer ─────────────────────────────────────────────────────────
    "research_agent":            {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "pattern_matcher":           {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "temporal_agent":            {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Company Layer ──────────────────────────────────────────────────────────
    "company_intelligence":      {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Layer 3 — Sentiment Aggregator ────────────────────────────────────────
    "sentiment_aggregator":      {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Portfolio & Tax ────────────────────────────────────────────────────────
    "portfolio_agent":           {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "tax_agent":                 {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Validation Layer ───────────────────────────────────────────────────────
    "critic_agent":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "watchdog":                  {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Output & Feedback ──────────────────────────────────────────────────────
    "investment_manager":        {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "performance_tracker":       {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── What If Simulator ─────────────────────────────────────────────────────
    "whatif_agent":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── GraphRAG Enricher ─────────────────────────────────────────────────────
    "graphrag_enricher":         {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Data Scrapers ─────────────────────────────────────────────────────────
    "data_scraper":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Technical Analysis (Candlestick + Volatility) ─────────────────────────
    "technical_analysis_agent":  {"provider": "groq",       "model": "llama-3.3-70b-versatile"},

    # ── Plain Language Formatter ──────────────────────────────────────────────
    "plain_language_formatter":  {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "market_intelligence":       {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "free_data_feeds":           {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
}

DEFAULT_MODEL = {"provider": "groq", "model": "llama-3.3-70b-versatile"}

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
        # FIX: removed fallback to discontinued qwen model
        # now falls back to mistral which is free and working on OpenRouter
        if "429" in str(e) or "rate_limit" in str(e):
            logger.warning("groq.rate_limit_hit_falling_back_to_openrouter")
            return await _call_openrouter(prompt, "mistralai/mistral-7b-instruct:free")
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
      groq       → all agents use Groq Llama (default, testing)
      anthropic  → all agents use Claude (production)
      kaggle     → all agents use Ollama/Gemma on Kaggle via ngrok tunnel
      auto       → each agent uses its designated model
    """
    global_provider = os.getenv("AI_PROVIDER", "groq")

    if global_provider == "anthropic":
        model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        text = await _call_anthropic(prompt, model_name)
        return _clean(text)

    if global_provider == "groq":
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        text = await _call_groq(prompt, model_name)
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
            text = await _call_groq(prompt, "llama-3.3-70b-versatile")

        return _clean(text)

    except Exception as e:
        log.error("llm_client.error", error=str(e))
        if provider != "groq":
            log.warning("llm_client.fallback_to_groq")
            try:
                text = await _call_groq(prompt, "llama-3.3-70b-versatile")
                return _clean(text)
            except Exception as fe:
                log.error("llm_client.fallback_failed", error=str(fe))
        raise


def _clean(text: str) -> str:
    if not text:
        return "{}"
    return text.strip().replace("```json", "").replace("```", "").strip()

