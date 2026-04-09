"""Test that Signal model has credibility columns."""
import pytest
from models.models import Signal


def test_signal_has_credibility_score():
    s = Signal(title="Test", credibility_score=0.85)
    assert s.credibility_score == 0.85


def test_signal_has_claim_type():
    s = Signal(title="Test", claim_type="factual")
    assert s.claim_type == "factual"


def test_signal_has_source_urls():
    s = Signal(title="Test", source_urls=["https://reuters.com/article1"])
    assert s.source_urls == ["https://reuters.com/article1"]


def test_signal_has_corroboration_count():
    s = Signal(title="Test", corroboration_count=3)
    assert s.corroboration_count == 3


def test_signal_credibility_defaults():
    s = Signal(title="Test")
    assert s.credibility_score is None
    assert s.claim_type is None
    assert s.corroboration_count == 0
