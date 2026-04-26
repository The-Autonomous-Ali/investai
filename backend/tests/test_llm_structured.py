"""Retry / fallback behaviour for call_llm_structured."""
import pytest
from unittest.mock import AsyncMock, patch
from pydantic import BaseModel

from utils.llm_client import call_llm_structured


class _Echo(BaseModel):
    x: int


@pytest.mark.asyncio
async def test_returns_immediately_on_valid_first_response():
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock_call, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_call.return_value = '{"x": 7}'
        result = await call_llm_structured("p", _Echo, max_retries=3)
    assert result.x == 7
    assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_retries_on_bad_json_then_succeeds():
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock_call, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_call.side_effect = ["not json", "still bad", '{"x": 1}']
        result = await call_llm_structured("p", _Echo, max_retries=3, fallback_provider=None)
    assert result.x == 1
    assert mock_call.call_count == 3


@pytest.mark.asyncio
async def test_falls_back_to_other_provider_after_exhausting_retries():
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock_primary, \
         patch("utils.llm_client._call_openrouter", new_callable=AsyncMock) as mock_fb, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_primary.side_effect = ["bad", "bad", "bad"]
        mock_fb.return_value = '{"x": 42}'
        result = await call_llm_structured("p", _Echo, max_retries=3, fallback_provider="openrouter")
    assert result.x == 42
    assert mock_primary.call_count == 3
    assert mock_fb.call_count == 1


@pytest.mark.asyncio
async def test_raises_when_all_attempts_and_fallback_fail():
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock_primary, \
         patch("utils.llm_client._call_openrouter", new_callable=AsyncMock) as mock_fb, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_primary.side_effect = ["bad", "bad", "bad"]
        mock_fb.return_value = "also bad"
        with pytest.raises(Exception):
            await call_llm_structured("p", _Echo, max_retries=3, fallback_provider="openrouter")


@pytest.mark.asyncio
async def test_provider_exception_breaks_out_of_retry_loop():
    """Network/rate-limit errors should not consume retries — go straight to fallback."""
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock_primary, \
         patch("utils.llm_client._call_openrouter", new_callable=AsyncMock) as mock_fb, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_primary.side_effect = RuntimeError("rate_limit hit")
        mock_fb.return_value = '{"x": 9}'
        result = await call_llm_structured("p", _Echo, max_retries=3, fallback_provider="openrouter")
    assert result.x == 9
    assert mock_primary.call_count == 1
    assert mock_fb.call_count == 1
