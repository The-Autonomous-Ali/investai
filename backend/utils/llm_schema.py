"""
JSON repair + Pydantic validation for LLM outputs.

LLM responses are notoriously brittle when fed straight into json.loads —
models add markdown code fences, leave trailing commas, or include leading
"Here is the JSON:" prose. parse_and_validate strips the common offenders
and then validates against a Pydantic schema so callers get a typed object
or a clear ValidationError.
"""
import json
import re

import structlog
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger()


_FENCE_RE = re.compile(r"^```(?:json|JSON)?\s*|\s*```\s*$", re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_LEADING_PROSE_RE = re.compile(r"^[^{\[]*(?=[{\[])", re.DOTALL)


def repair_json(raw: str) -> str:
    """Strip markdown fences, leading prose, and common syntax errors."""
    if not raw:
        return ""
    text = raw.strip()
    text = _FENCE_RE.sub("", text).strip()
    # Drop any leading "Here is the JSON:" style prefix before the first { or [
    text = _LEADING_PROSE_RE.sub("", text, count=1) or text
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text.strip()


def parse_and_validate(raw: str, schema: type[BaseModel]) -> BaseModel:
    """Parse JSON string and validate against a Pydantic schema.

    Raises ValidationError on either JSON decode or schema validation failure
    so callers can use a single except clause for retry logic.
    """
    repaired = repair_json(raw)
    try:
        data = json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.warning(
            "llm_schema.json_decode_failed",
            schema=schema.__name__,
            raw_preview=repaired[:200],
            error=str(e),
        )
        raise ValidationError.from_exception_data(
            title=schema.__name__,
            line_errors=[
                {
                    "type": "value_error",
                    "loc": ("__root__",),
                    "input": repaired[:200],
                    "ctx": {"error": f"Invalid JSON: {e}"},
                }
            ],
        )
    return schema.model_validate(data)
