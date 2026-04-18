"""Signal extractor consumer — reads `signals.raw`, LLM-extracts, writes to DB.

Pipeline position:
    [connectors] --XADD--> signals.raw --XREADGROUP--> signal_extractor --INSERT--> signals table

Responsibilities:
    1. Pull a batch of raw messages from the Redis Stream.
    2. For each, call the LLM to classify + extract structured fields.
    3. Insert a Signal row. Postgres `content_hash` unique constraint is
       the FINAL dedup gate — InsertError on duplicate is expected, not
       an error.
    4. XACK the message either way (even on extraction failure, so we
       don't loop forever on a poison message).

This replaces the inline classification logic in `agents/signal_watcher.py`
for all feeds that flow through the new Stream pipeline. The old watcher
stays for now; migration will happen in D2.

Consumer name: comes from HOSTNAME env or a generated UUID. Multiple
extractor processes can run concurrently safely — each gets a unique
consumer name and Redis hands out disjoint messages.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from typing import Optional

import structlog
from sqlalchemy.exc import IntegrityError

from ingestion.redis_client import get_client
from models.models import Signal, SignalType, SignalUrgency

logger = structlog.get_logger()

# Don't persist signals below this score — saves DB bloat on noise.
MIN_IMPORTANCE_TO_PERSIST = 2.0

# Batch size per XREADGROUP call.
DEFAULT_BATCH_SIZE = 10

# Block time on empty stream (milliseconds). Short-ish so shutdown is snappy.
DEFAULT_BLOCK_MS = 5000

# Cap on body length fed to the LLM (characters). Raw body already capped
# at ingestion, but belt-and-braces in case a scrape subclass ignores that.
MAX_BODY_FOR_LLM = 4000


EXTRACTION_PROMPT = """You extract structured financial signals from raw feed items.

Return ONLY valid JSON (no markdown, no preamble, no trailing commentary).

Item:
  source_name: {source_name}
  source_region: {source_region}
  source_tier: {source_tier}
  category: {category}
  title: {title}
  body: {body}

Schema:
{{
  "signal_type": "geopolitical|monetary|fiscal|commodity|currency|corporate|natural_disaster|trade",
  "urgency": "breaking|developing|long_term",
  "importance_score": 0.0-10.0,
  "confidence": 0.0-1.0,
  "geography": "global|regional|india|us|europe|china|middle_east",
  "sentiment": "positive|negative|neutral",
  "claim_type": "factual|analysis|opinion|tip",
  "entities_mentioned": ["Fed", "Oil", "RBI"],
  "sectors_affected": {{"aviation": "negative", "energy": "positive"}},
  "india_impact_reasoning": "Why this matters for Indian markets (1-2 sentences).",
  "second_order_effects": ["step 1 -> step 2 -> step 3"]
}}

Rules:
  - claim_type=tip MUST be used for any trading/pump/buy-sell recommendation.
  - importance_score 0-2 = noise/filler; 3-5 = normal news; 6-8 = material;
    9-10 = rare, reserved for market-moving shocks.
  - If there is NO meaningful financial signal, return:
    {{"importance_score": 0, "signal_type": "trade", "urgency": "long_term",
      "confidence": 0.0, "geography": "global", "sentiment": "neutral",
      "claim_type": "opinion", "entities_mentioned": [],
      "sectors_affected": {{}}, "india_impact_reasoning": "none",
      "second_order_effects": []}}
"""


class SignalExtractor:
    """One instance per extractor process. Pull -> LLM -> DB -> ack."""

    def __init__(
        self,
        consumer_name: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        block_ms: int = DEFAULT_BLOCK_MS,
        min_importance: float = MIN_IMPORTANCE_TO_PERSIST,
    ) -> None:
        self.consumer_name = consumer_name or self._default_consumer_name()
        self.batch_size = batch_size
        self.block_ms = block_ms
        self.min_importance = min_importance
        self._stopped = False
        self._log = logger.bind(consumer=self.consumer_name)

    @staticmethod
    def _default_consumer_name() -> str:
        host = os.getenv("HOSTNAME") or socket.gethostname() or "extractor"
        return f"{host}-{uuid.uuid4().hex[:8]}"

    async def run_forever(self) -> None:
        """Loop until `stop()` is called. Safe across Redis outages."""
        redis = get_client()
        await redis.ensure_group()
        self._log.info("signal_extractor.started")

        while not self._stopped:
            try:
                await self.run_once()
            except Exception as e:  # paranoia — never let the loop die
                self._log.warning("signal_extractor.loop_error", error=str(e))
                await asyncio.sleep(2.0)

        self._log.info("signal_extractor.stopped")

    def stop(self) -> None:
        self._stopped = True

    async def run_once(self) -> int:
        """Pull and process one batch. Returns number of signals persisted."""
        redis = get_client()
        messages = await redis.xread_group(
            consumer=self.consumer_name,
            count=self.batch_size,
            block_ms=self.block_ms,
        )
        if not messages:
            return 0

        persisted = 0
        for msg_id, fields in messages:
            try:
                was_persisted = await self._process_one(fields)
                if was_persisted:
                    persisted += 1
            except Exception as e:
                # Per-message failure should never block the batch or
                # leave a poison message pending forever. Log + ack.
                self._log.warning(
                    "signal_extractor.process_failed",
                    msg_id=msg_id,
                    error=str(e),
                )
            finally:
                await redis.xack(msg_id)

        if persisted:
            self._log.info(
                "signal_extractor.batch_complete",
                processed=len(messages),
                persisted=persisted,
            )
        return persisted

    async def _process_one(self, fields: dict) -> bool:
        """Classify one message and persist if important enough.

        Returns True if a Signal row was inserted. False on:
            - importance below threshold
            - LLM extraction failure
            - duplicate (content_hash already in DB)
            - missing required fields
        """
        required = ("source_name", "title", "content_hash")
        for k in required:
            if not fields.get(k):
                self._log.debug("signal_extractor.skip_missing_field", field=k)
                return False

        extracted = await self._extract(fields)
        if extracted is None:
            return False

        score = float(extracted.get("importance_score", 0) or 0)
        if score < self.min_importance:
            return False

        return await self._insert_signal(fields, extracted)

    async def _extract(self, fields: dict) -> Optional[dict]:
        """Call LLM and return parsed dict, or None on failure."""
        # Lazy import so cold-start cost stays in worker, not at module load.
        from utils.llm_client import call_llm

        body = (fields.get("body") or "")[:MAX_BODY_FOR_LLM]
        prompt = EXTRACTION_PROMPT.format(
            source_name=fields.get("source_name", ""),
            source_region=fields.get("source_region", ""),
            source_tier=fields.get("source_tier", ""),
            category=fields.get("category", ""),
            title=fields.get("title", ""),
            body=body,
        )

        try:
            response = await call_llm(prompt, agent_name="signal_extractor")
        except Exception as e:
            self._log.warning("signal_extractor.llm_failed", error=str(e))
            return None

        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            # LLM sometimes wraps in ```json ... ```. Try stripping.
            cleaned = self._strip_code_fences(response)
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, TypeError):
                self._log.warning(
                    "signal_extractor.llm_bad_json",
                    sample=(response or "")[:200],
                )
                return None

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        if not text:
            return ""
        t = text.strip()
        if t.startswith("```"):
            # Drop the opening fence (```json or ```)
            first_newline = t.find("\n")
            if first_newline != -1:
                t = t[first_newline + 1 :]
        if t.endswith("```"):
            t = t[:-3]
        return t.strip()

    async def _insert_signal(self, fields: dict, extracted: dict) -> bool:
        """Insert a Signal row. Returns False on duplicate (unique violation)."""
        # Lazy import — the DB engine creation at module load would pull
        # asyncpg into the import graph, which is unnecessary for unit
        # tests and harmful if the driver isn't installed in CI.
        from database.connection import AsyncSessionLocal

        signal_type = self._coerce_enum(
            extracted.get("signal_type"), SignalType, SignalType.CORPORATE
        )
        urgency = self._coerce_enum(
            extracted.get("urgency"), SignalUrgency, SignalUrgency.LONG_TERM
        )

        row = Signal(
            title=fields.get("title", "")[:500],
            content=(fields.get("body") or "")[:8000],
            source=fields.get("source_name"),
            source_agent="signal_extractor",
            source_tier=self._safe_int(fields.get("source_tier")),
            source_region=fields.get("source_region"),
            signal_type=signal_type,
            urgency=urgency,
            importance_score=self._safe_float(extracted.get("importance_score")),
            confidence=self._safe_float(extracted.get("confidence")),
            geography=extracted.get("geography"),
            sentiment=extracted.get("sentiment"),
            claim_type=extracted.get("claim_type"),
            entities_mentioned=extracted.get("entities_mentioned") or [],
            sectors_affected=extracted.get("sectors_affected") or {},
            india_impact_analysis=extracted.get("india_impact_reasoning"),
            chain_effects=extracted.get("second_order_effects") or [],
            content_hash=fields.get("content_hash"),
            source_urls=[fields.get("url")] if fields.get("url") else [],
        )

        async with AsyncSessionLocal() as session:
            try:
                session.add(row)
                await session.commit()
                return True
            except IntegrityError:
                # content_hash already seen — expected, not an error.
                await session.rollback()
                self._log.debug(
                    "signal_extractor.duplicate_skipped",
                    content_hash=fields.get("content_hash"),
                )
                return False
            except Exception as e:
                await session.rollback()
                self._log.warning(
                    "signal_extractor.insert_failed",
                    error=str(e),
                )
                return False

    @staticmethod
    def _coerce_enum(value, enum_cls, default):
        if not value:
            return default
        try:
            return enum_cls(value)
        except ValueError:
            return default

    @staticmethod
    def _safe_float(v) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(v) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
