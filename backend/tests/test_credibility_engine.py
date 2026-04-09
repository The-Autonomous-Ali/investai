"""Tests for the credibility scoring engine."""
import pytest
from agents.credibility_engine import CredibilityEngine

@pytest.fixture
def engine():
    return CredibilityEngine()

# Source Score Tests
def test_source_score_tier1_rbi(engine):
    assert engine.get_source_score("RBI", tier=1) == 0.95

def test_source_score_tier2_reuters(engine):
    assert engine.get_source_score("Reuters Business", tier=2) == 0.85

def test_source_score_tier3(engine):
    assert engine.get_source_score("OilPrice.com", tier=3) == 0.60

def test_source_score_unknown(engine):
    assert engine.get_source_score("RandomBlog", tier=4) == 0.30

def test_source_score_google_news(engine):
    assert engine.get_source_score("Google News", tier=3) == 0.40

# Claim Type Weight Tests
def test_claim_weight_factual(engine):
    assert engine.get_claim_weight("factual") == 1.0

def test_claim_weight_analysis(engine):
    assert engine.get_claim_weight("analysis") == 0.7

def test_claim_weight_opinion(engine):
    assert engine.get_claim_weight("opinion") == 0.4

def test_claim_weight_tip_rejected(engine):
    assert engine.get_claim_weight("tip") == 0.0

def test_claim_weight_unknown_defaults_to_analysis(engine):
    assert engine.get_claim_weight("unknown") == 0.7

# Corroboration Multiplier Tests
def test_corroboration_3_plus_sources(engine):
    assert engine.get_corroboration_multiplier(3) == 1.3

def test_corroboration_2_sources(engine):
    assert engine.get_corroboration_multiplier(2) == 1.1

def test_corroboration_single_source(engine):
    assert engine.get_corroboration_multiplier(1) == 0.8

def test_corroboration_zero_sources(engine):
    assert engine.get_corroboration_multiplier(0) == 0.8

# Final Score Tests
def test_final_score_gold_factual_corroborated(engine):
    score = engine.compute_credibility(source_name="RBI", tier=1, claim_type="factual", corroboration_count=3)
    assert score == 1.0  # 0.95 * 1.0 * 1.3 = 1.235 → capped at 1.0

def test_final_score_silver_opinion_single(engine):
    score = engine.compute_credibility(source_name="Moneycontrol", tier=2, claim_type="opinion", corroboration_count=1)
    assert round(score, 2) == 0.24  # 0.75 * 0.4 * 0.8 = 0.24

def test_final_score_tip_always_zero(engine):
    score = engine.compute_credibility(source_name="RBI", tier=1, claim_type="tip", corroboration_count=5)
    assert score == 0.0

def test_final_score_threshold(engine):
    score = engine.compute_credibility(source_name="RandomBlog", tier=4, claim_type="opinion", corroboration_count=1)
    assert score < 0.5
    assert engine.passes_threshold(score) is False

def test_passes_threshold(engine):
    assert engine.passes_threshold(0.6) is True
    assert engine.passes_threshold(0.5) is True
    assert engine.passes_threshold(0.49) is False
