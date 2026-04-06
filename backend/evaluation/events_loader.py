"""Load and validate the historical_events.yaml catalog."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from models.models import SignalType

_VALID_SIGNAL_TYPES: set[str] = {t.value for t in SignalType}

_REQUIRED_FIELDS: set[str] = {
    "date", "signal_type", "event_name", "entities", "description", "source_url",
}


@dataclass(frozen=True)
class HistoricalEvent:
    date: date
    signal_type: str        # matches SignalType enum values
    event_name: str         # must match a Neo4j Event.name
    entities: tuple[str, ...]
    description: str
    source_url: str


class EventValidationError(ValueError):
    pass


def validate_event(raw: dict) -> HistoricalEvent:
    """Strict schema check. Unknown keys rejected; missing fields rejected."""
    if not isinstance(raw, dict):
        raise EventValidationError(f"event must be a dict, got {type(raw).__name__}")

    keys = set(raw.keys())
    missing = _REQUIRED_FIELDS - keys
    if missing:
        raise EventValidationError(f"missing required fields: {sorted(missing)}")
    extra = keys - _REQUIRED_FIELDS
    if extra:
        raise EventValidationError(f"unknown fields: {sorted(extra)}")

    d = raw["date"]
    if isinstance(d, datetime):
        d = d.date()
    elif isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError as e:
            raise EventValidationError(f"bad ISO date: {raw['date']!r}") from e
    elif not isinstance(d, date):
        raise EventValidationError(f"date must be ISO string or date, got {type(d).__name__}")

    stype = raw["signal_type"]
    if stype not in _VALID_SIGNAL_TYPES:
        raise EventValidationError(
            f"signal_type {stype!r} not in {sorted(_VALID_SIGNAL_TYPES)}"
        )

    event_name = raw["event_name"]
    if not isinstance(event_name, str) or not event_name.strip():
        raise EventValidationError("event_name must be a non-empty string")

    entities = raw["entities"]
    if not isinstance(entities, list) or not all(isinstance(e, str) for e in entities):
        raise EventValidationError("entities must be a list of strings")

    description = raw["description"]
    if not isinstance(description, str):
        raise EventValidationError("description must be a string")

    source_url = raw["source_url"]
    if not isinstance(source_url, str):
        raise EventValidationError("source_url must be a string")

    return HistoricalEvent(
        date=d,
        signal_type=stype,
        event_name=event_name,
        entities=tuple(entities),
        description=description,
        source_url=source_url,
    )


def load_events(path: Path | None = None) -> list[HistoricalEvent]:
    """Load and validate every entry in the YAML catalog."""
    if path is None:
        path = Path(__file__).parent / "historical_events.yaml"
    with path.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    if not isinstance(doc, dict) or "events" not in doc:
        raise EventValidationError("YAML root must be a mapping with an 'events' key")

    raw_events = doc["events"]
    if not isinstance(raw_events, list):
        raise EventValidationError("'events' must be a list")

    out: list[HistoricalEvent] = []
    for i, raw in enumerate(raw_events):
        try:
            out.append(validate_event(raw))
        except EventValidationError as e:
            raise EventValidationError(f"event #{i}: {e}") from e
    return out
