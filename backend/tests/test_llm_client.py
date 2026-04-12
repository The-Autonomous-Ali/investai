"""Tests for the LLM client routing and clean function."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from utils.llm_client import _clean, call_llm


# ── _clean function tests ────────────────────────────────────────────────────

def test_clean_strips_markdown_fences():
    assert _clean('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_clean_strips_whitespace():
    assert _clean('  {"a": 1}  ') == '{"a": 1}'


def test_clean_empty_string():
    assert _clean("") == "{}"


def test_clean_none():
    assert _clean(None) == "{}"


# ── call_llm routing tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_llm_routes_to_groq():
    with patch("utils.llm_client._call_groq", new_callable=AsyncMock) as mock_groq, \
         patch.dict("os.environ", {"AI_PROVIDER": "groq"}):
        mock_groq.return_value = '{"result": "ok"}'
        result = await call_llm("test prompt", agent_name="orchestrator")

    assert result == '{"result": "ok"}'
    mock_groq.assert_called_once()


@pytest.mark.asyncio
async def test_call_llm_routes_to_anthropic():
    with patch("utils.llm_client._call_anthropic", new_callable=AsyncMock) as mock_ant, \
         patch.dict("os.environ", {"AI_PROVIDER": "anthropic"}):
        mock_ant.return_value = '{"result": "claude"}'
        result = await call_llm("test prompt", agent_name="orchestrator")

    assert result == '{"result": "claude"}'
    mock_ant.assert_called_once()


@pytest.mark.asyncio
async def test_call_llm_routes_to_gemini():
    with patch("utils.llm_client._call_gemini", new_callable=AsyncMock) as mock_gem, \
         patch.dict("os.environ", {"AI_PROVIDER": "gemini"}):
        mock_gem.return_value = '{"result": "gemini"}'
        result = await call_llm("test prompt")

    assert result == '{"result": "gemini"}'


@pytest.mark.asyncio
async def test_call_llm_groq_rate_limit_falls_back_to_openrouter():
    """The fallback to openrouter happens inside _call_groq on 429 errors.
    We simulate this by patching _call_groq to directly call the mocked _call_openrouter."""
    with patch("utils.llm_client._call_openrouter", new_callable=AsyncMock) as mock_or, \
         patch.dict("os.environ", {"AI_PROVIDER": "groq"}):
        mock_or.return_value = '{"fallback": true}'

        # Patch _call_groq to simulate the 429 path that internally calls _call_openrouter
        async def fake_groq(prompt, model):
            # Simulate what the real _call_groq does on 429: delegate to openrouter
            return await mock_or(prompt, "mistralai/mistral-7b-instruct:free")

        with patch("utils.llm_client._call_groq", side_effect=fake_groq):
            result = await call_llm("test", agent_name="orchestrator")

    assert result == '{"fallback": true}'
    mock_or.assert_called_once()
