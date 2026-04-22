from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.models import EventStage
from services.signal_monitor import _detect_change, create_signal_links_for_advice


def build_link(*, status="active", stage_at_advice="active", importance=8.5):
    return SimpleNamespace(
        advice_id="advice-1",
        signal_id="signal-1",
        signal_title="Oil spike",
        stage_at_advice=stage_at_advice,
        importance_at_advice=importance,
        current_status=status,
    )


def build_signal(*, stage=EventStage.ACTIVE, importance=8.5):
    return SimpleNamespace(
        stage=stage,
        importance_score=importance,
    )


def test_detect_change_marks_first_escalation():
    link = build_link(stage_at_advice="active", status="active")
    current_signal = build_signal(stage=EventStage.ESCALATING)

    change = _detect_change(link, current_signal)

    assert change["new_status"] == "escalated"
    assert change["severity"] == "urgent"


def test_detect_change_suppresses_duplicate_escalation_alerts():
    link = build_link(stage_at_advice="active", status="escalated")
    current_signal = build_signal(stage=EventStage.ESCALATING)

    change = _detect_change(link, current_signal)

    assert change is None


def test_detect_change_can_resolve_after_prior_escalation():
    link = build_link(stage_at_advice="active", status="escalated")
    current_signal = build_signal(stage=EventStage.RESOLVED)

    change = _detect_change(link, current_signal)

    assert change["new_status"] == "resolved"
    assert "resolved" in change["description"].lower()


def test_detect_change_flags_large_importance_drop():
    link = build_link(stage_at_advice="active", importance=8.5)
    current_signal = build_signal(stage=EventStage.ACTIVE, importance=6.0)

    change = _detect_change(link, current_signal)

    assert change["new_status"] == "weakened"
    assert change["severity"] == "info"


@pytest.mark.asyncio
async def test_create_signal_links_normalizes_stage_values():
    db = SimpleNamespace(
        add=MagicMock(),
        flush=AsyncMock(),
    )

    await create_signal_links_for_advice(
        db,
        "advice-1",
        [
            {
                "id": "signal-1",
                "title": "Oil spike",
                "stage": "ESCALATING",
            }
        ],
    )

    link = db.add.call_args[0][0]
    assert link.stage_at_advice == "escalating"
    db.flush.assert_awaited_once()
