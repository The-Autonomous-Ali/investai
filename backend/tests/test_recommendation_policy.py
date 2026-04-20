"""Tests for the deterministic recommendation policy layer."""
from services.recommendation_policy import RecommendationPolicy


def build_analysis(*, buy_sector="Power", avoid_sector=None):
    analysis = {
        "confidence_score": 0.72,
        "signals_used": [
            "Power demand remains firm across India.",
            "Fuel costs are stable after a volatile quarter.",
        ],
        "what_could_go_wrong": [
            "Policy support weakens.",
            "Demand growth slows below expectations.",
        ],
        "global_macro_summary": "Domestic power demand and infrastructure spending remain supportive.",
        "root_cause_narrative": "Power demand is holding up because industrial and data-center usage remains firm.",
        "sectors_to_buy": [
            {
                "sector": buy_sector,
                "reason": "Demand visibility is improving and sector-level support remains intact.",
            }
        ],
        "sectors_to_avoid": [],
        "company_picks": [
            {
                "sector": buy_sector,
                "signal_fit_score": 8.6,
                "signal_fit_reason": "The sector still maps cleanly to the active signal set.",
                "companies": [
                    {
                        "name": "Adani Power",
                        "nse_symbol": "ADANIPOWER",
                        "type": "established",
                    }
                ],
                "etf_alternative": {
                    "name": "Nifty Energy ETF",
                    "symbol": "ENERGYETF",
                },
            }
        ],
        "rebalancing_triggers": [
            {
                "condition": "Industrial power demand breaks below trend",
                "implication": "Review the thesis before adding more capital.",
            }
        ],
        "review_date": "2026-05-15",
        "disclaimer": "Educational analysis only.",
    }

    if avoid_sector:
        analysis["sectors_to_avoid"] = [
            {
                "sector": avoid_sector,
                "reason": "The sector is now facing weakening support and higher downside risk.",
            }
        ]

    return analysis


def build_profile(*, risk="moderate", holdings=None, total_value=0):
    return {
        "risk_tolerance": risk,
        "current_holdings_detail": holdings or [],
        "portfolio_summary": {
            "total_current_value": total_value,
        },
    }


def build_holding(*, name="Adani Power", symbol="ADANIPOWER", sector="Power", current_value=20000, weight_pct=10):
    return {
        "name": name,
        "symbol": symbol,
        "sector": sector,
        "instrument_type": "stock",
        "quantity": 20,
        "current_value": current_value,
        "weight_pct": weight_pct,
    }


def test_deploy_cash_uses_etf_and_keeps_reserve_for_conservative_user():
    policy = RecommendationPolicy()
    recommendation = policy.build(
        query="I have 50000 to invest. Where should I invest it?",
        amount=50000,
        horizon="1 year",
        country="India",
        user_profile=build_profile(risk="conservative"),
        analysis=build_analysis(),
    )

    assert recommendation["query_type"] == "deploy_cash"
    assert recommendation["action"] == "deploy"
    assert any(move["instrument_type"] == "etf" for move in recommendation["recommended_moves"])
    assert any(move["instrument"] == "Cash Reserve" for move in recommendation["recommended_moves"])


def test_position_review_allows_add_for_verified_positive_holding():
    policy = RecommendationPolicy()
    holding = build_holding(current_value=20000, weight_pct=10)
    recommendation = policy.build(
        query="I have 20 stocks of Adani Power. Should I invest more?",
        amount=0,
        horizon="1 year",
        country="India",
        user_profile=build_profile(risk="moderate", holdings=[holding], total_value=200000),
        analysis=build_analysis(),
    )

    assert recommendation["query_type"] == "position_review"
    assert recommendation["action"] == "add"
    assert recommendation["current_position"]["symbol"] == "ADANIPOWER"


def test_position_review_exits_when_negative_signals_hit_high_concentration_holding():
    policy = RecommendationPolicy()
    holding = build_holding(current_value=80000, weight_pct=40)
    recommendation = policy.build(
        query="I hold Adani Power. Should I keep it or sell it?",
        amount=0,
        horizon="1 year",
        country="India",
        user_profile=build_profile(risk="moderate", holdings=[holding], total_value=200000),
        analysis=build_analysis(avoid_sector="Power"),
    )

    assert recommendation["action"] == "exit"
    assert recommendation["action_strength"] == "high"
    assert recommendation["suitability_checks"]["concentration"] == "high"


def test_unmatched_position_review_degrades_to_watch_instead_of_forcing_decision():
    policy = RecommendationPolicy()
    recommendation = policy.build(
        query="I have 10 shares of Unknown Infra. Should I keep or sell?",
        amount=0,
        horizon="1 year",
        country="India",
        user_profile=build_profile(
            holdings=[build_holding(name="Reliance Industries", symbol="RELIANCE", sector="Oil & Gas")],
            total_value=150000,
        ),
        analysis=build_analysis(),
    )

    assert recommendation["query_type"] == "position_review"
    assert recommendation["action"] == "watch"
    assert recommendation["current_position"] is None
    assert any("could not confidently match" in limit.lower() for limit in recommendation["known_limits"])


def test_deploy_cash_without_amount_returns_watch():
    policy = RecommendationPolicy()
    recommendation = policy.build(
        query="Where should I invest this money?",
        amount=0,
        horizon="1 year",
        country="India",
        user_profile=build_profile(risk="moderate"),
        analysis=build_analysis(),
    )

    assert recommendation["query_type"] == "deploy_cash"
    assert recommendation["action"] == "watch"
    assert recommendation["recommended_moves"] == []
