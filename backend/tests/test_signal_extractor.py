"""Unit tests for SignalExtractor — mocks Redis, LLM, and DB."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_redis():
    fake = MagicMock()
    fake.connect = AsyncMock()
    fake.ensure_group = AsyncMock()
    fake.xread_group = AsyncMock(return_value=[])
    fake.xack = AsyncMock(return_value=True)
    return fake


def _signal_fields(**overrides):
    base = {
        "source_name": "fed-monetary",
        "source_region": "us",
        "source_tier": "1",
        "category": "monetary",
        "url": "https://federalreserve.gov/abc",
        "title": "Fed raises rates by 25bps",
        "body": "The FOMC raised the federal funds rate target range by 25 basis points.",
        "fetched_at": "2026-04-18T00:00:00+00:00",
        "published_at": "2026-04-17T18:00:00+00:00",
        "raw_payload": "",
        "content_hash": "abc123def",
    }
    base.update(overrides)
    return base


def _llm_response(score: float = 7.0, signal_type: str = "monetary"):
    return json.dumps({
        "signal_type": signal_type,
        "urgency": "breaking",
        "importance_score": score,
        "confidence": 0.85,
        "geography": "us",
        "sentiment": "negative",
        "claim_type": "factual",
        "entities_mentioned": ["Fed", "FOMC"],
        "sectors_affected": {"banking": "positive", "tech": "negative"},
        "india_impact_reasoning": "Higher US rates pressure FPI flows into India.",
        "second_order_effects": ["rate hike -> stronger USD -> INR weakens"],
    })


@pytest.fixture(autouse=True)
def patch_deps():
    fake_redis = _fake_redis()

    # Fake async session context manager.
    fake_session = MagicMock()
    fake_session.add = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()

    class _CtxFactory:
        def __call__(self):
            return self
        async def __aenter__(self):
            return fake_session
        async def __aexit__(self, *a):
            return None

    with patch("ingestion.signal_extractor.get_client", return_value=fake_redis), \
         patch("ingestion.signal_extractor.AsyncSessionLocal", _CtxFactory()):
        yield {
            "redis": fake_redis,
            "session": fake_session,
        }


@pytest.mark.asyncio
async def test_run_once_persists_signal_above_threshold(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])

    with patch("utils.llm_client.call_llm", AsyncMock(return_value=_llm_response(7.0))):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 1
    patch_deps["session"].add.assert_called_once()
    patch_deps["session"].commit.assert_awaited_once()
    patch_deps["redis"].xack.assert_awaited_once_with("1-0")


@pytest.mark.asyncio
async def test_run_once_skips_low_importance(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])

    with patch("utils.llm_client.call_llm", AsyncMock(return_value=_llm_response(1.0))):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 0
    patch_deps["session"].add.assert_not_called()
    # Still ack'd — we don't want to re-process a low-score message.
    patch_deps["redis"].xack.assert_awaited_once_with("1-0")


@pytest.mark.asyncio
async def test_run_once_acks_even_when_llm_fails(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])

    with patch("utils.llm_client.call_llm", AsyncMock(side_effect=RuntimeError("rate limit"))):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 0
    patch_deps["redis"].xack.assert_awaited_once()  # poison must not stick


@pytest.mark.asyncio
async def test_run_once_handles_malformed_llm_json(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])

    with patch("utils.llm_client.call_llm", AsyncMock(return_value="not valid json {")):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 0
    patch_deps["redis"].xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_strips_markdown_code_fences(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])
    wrapped = f"```json\n{_llm_response(6.5)}\n```"

    with patch("utils.llm_client.call_llm", AsyncMock(return_value=wrapped)):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 1


@pytest.mark.asyncio
async def test_run_once_duplicate_returns_false(patch_deps):
    from sqlalchemy.exc import IntegrityError
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])
    patch_deps["session"].commit = AsyncMock(
        side_effect=IntegrityError("dup", None, Exception())
    )

    with patch("utils.llm_client.call_llm", AsyncMock(return_value=_llm_response(7.0))):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 0
    patch_deps["redis"].xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_once_skips_message_missing_required_field(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    bad = _signal_fields(title="")
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", bad),
    ])

    with patch("utils.llm_client.call_llm", AsyncMock(return_value=_llm_response(7.0))) as llm:
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 0
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_run_once_empty_batch_returns_zero(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    # xread_group default already returns []
    extractor = SignalExtractor(consumer_name="test-consumer")
    persisted = await extractor.run_once()
    assert persisted == 0


@pytest.mark.asyncio
async def test_invalid_enum_falls_back_to_default(patch_deps):
    from ingestion.signal_extractor import SignalExtractor
    patch_deps["redis"].xread_group = AsyncMock(return_value=[
        ("1-0", _signal_fields()),
    ])
    # signal_type="bogus" should not crash — falls back to CORPORATE.
    with patch("utils.llm_client.call_llm",
               AsyncMock(return_value=_llm_response(7.0, signal_type="bogus"))):
        extractor = SignalExtractor(consumer_name="test-consumer")
        persisted = await extractor.run_once()

    assert persisted == 1
