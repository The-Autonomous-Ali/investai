"""Tests for LLM JSON repair and Pydantic validation."""
import pytest
from pydantic import BaseModel, ValidationError

from utils.llm_schema import parse_and_validate, repair_json


class DummyOutput(BaseModel):
    action: str
    confidence: float


def test_parse_valid_json():
    result = parse_and_validate('{"action": "buy", "confidence": 0.9}', DummyOutput)
    assert result.action == "buy"
    assert result.confidence == 0.9


def test_repair_strips_markdown_fences():
    raw = '```json\n{"action": "buy", "confidence": 0.9}\n```'
    assert repair_json(raw) == '{"action": "buy", "confidence": 0.9}'


def test_repair_strips_leading_prose():
    raw = 'Here is the JSON:\n{"action": "buy", "confidence": 0.9}'
    assert repair_json(raw) == '{"action": "buy", "confidence": 0.9}'


def test_repair_fixes_trailing_comma():
    raw = '{"action": "buy", "confidence": 0.9,}'
    fixed = repair_json(raw)
    result = parse_and_validate(fixed, DummyOutput)
    assert result.confidence == 0.9


def test_parse_validates_via_schema():
    raw = '{"action": "buy", "confidence": 0.9}'
    out = parse_and_validate(raw, DummyOutput)
    assert isinstance(out, DummyOutput)


def test_parse_invalid_json_raises_validation_error():
    with pytest.raises(ValidationError):
        parse_and_validate("not json at all", DummyOutput)


def test_parse_missing_required_field_raises():
    with pytest.raises(ValidationError):
        parse_and_validate('{"action": "buy"}', DummyOutput)


def test_repair_handles_empty_string():
    assert repair_json("") == ""


def test_repair_handles_array_root():
    raw = '```json\n[1, 2, 3,]\n```'
    assert repair_json(raw) == "[1, 2, 3]"
