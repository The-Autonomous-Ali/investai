"""Unit tests for historical_events.yaml schema validation."""
from datetime import date
from pathlib import Path

import pytest
import yaml

from evaluation.events_loader import (
    EventValidationError,
    HistoricalEvent,
    load_events,
    validate_event,
)


def _valid_raw() -> dict:
    return {
        "date": "2022-02-24",
        "signal_type": "geopolitical",
        "event_name": "Global Risk Off",
        "entities": ["Russia", "Ukraine"],
        "description": "Russia invaded Ukraine.",
        "source_url": "https://example.com/",
    }


def test_valid_event_parses():
    e = validate_event(_valid_raw())
    assert isinstance(e, HistoricalEvent)
    assert e.date == date(2022, 2, 24)
    assert e.signal_type == "geopolitical"
    assert e.entities == ("Russia", "Ukraine")


def test_missing_field_rejected():
    raw = _valid_raw()
    del raw["source_url"]
    with pytest.raises(EventValidationError, match="missing required fields"):
        validate_event(raw)


def test_unknown_field_rejected():
    raw = _valid_raw()
    raw["extra"] = "nope"
    with pytest.raises(EventValidationError, match="unknown fields"):
        validate_event(raw)


def test_bad_signal_type_rejected():
    raw = _valid_raw()
    raw["signal_type"] = "meme"
    with pytest.raises(EventValidationError, match="signal_type"):
        validate_event(raw)


def test_bad_date_format_rejected():
    raw = _valid_raw()
    raw["date"] = "not-a-date"
    with pytest.raises(EventValidationError, match="bad ISO date"):
        validate_event(raw)


def test_entities_must_be_list_of_strings():
    raw = _valid_raw()
    raw["entities"] = "Russia, Ukraine"
    with pytest.raises(EventValidationError, match="entities"):
        validate_event(raw)


def test_empty_event_name_rejected():
    raw = _valid_raw()
    raw["event_name"] = "   "
    with pytest.raises(EventValidationError, match="event_name"):
        validate_event(raw)


def test_shipped_yaml_is_loadable():
    """The committed historical_events.yaml must parse cleanly. This is
    effectively a schema test on the real data file."""
    path = Path(__file__).resolve().parent.parent / "evaluation" / "historical_events.yaml"
    events = load_events(path)
    assert len(events) >= 30, "expected at least 30 seeded events"
    # All signal_types should be valid enum values (checked inside loader).
    # All dates should be before today.
    from datetime import date as _date
    today = _date.today()
    assert all(e.date <= today for e in events)


def test_load_events_wraps_index_in_error_message():
    """A broken event inside a list should surface its index."""
    bad_doc = {"events": [_valid_raw(), {**_valid_raw(), "signal_type": "nope"}]}
    # Round-trip through yaml to match load_events' path.
    import io
    text = yaml.safe_dump(bad_doc)
    p = Path("/tmp/_test_events.yaml")
    try:
        p.write_text(text, encoding="utf-8")
        with pytest.raises(EventValidationError, match="event #1"):
            load_events(p)
    finally:
        if p.exists():
            p.unlink()
