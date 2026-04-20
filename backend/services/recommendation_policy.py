"""Deterministic recommendation policy builder.

This module converts the raw multi-agent analysis package into a
canonical, user-facing recommendation contract. The goal is to keep the
final action decision reproducible and auditable instead of letting a
single LLM response directly choose "buy/sell/hold".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import uuid


POLICY_VERSION = "2026-04-20.v1"

POSITION_REVIEW_TERMS = {
    "hold", "keep", "sell", "trim", "exit", "invest more", "add more",
    "average", "holding", "shares", "stocks",
}
DEPLOY_CASH_TERMS = {
    "invest", "deploy", "allocate", "put money", "where should i invest",
    "50k", "100k", "50000", "100000",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class RecommendationPolicy:
    """Build a canonical recommendation from the raw analysis package."""

    def build(
        self,
        *,
        query: str,
        amount: float,
        horizon: str,
        country: str,
        user_profile: dict,
        analysis: dict,
    ) -> dict:
        query_context = self._classify_query(query, user_profile)
        confidence = self._compute_confidence(analysis, query_context)
        holdings = user_profile.get("current_holdings_detail", [])

        if query_context["query_type"] == "position_review":
            decision = self._build_position_review(
                query=query,
                analysis=analysis,
                user_profile=user_profile,
                query_context=query_context,
                confidence=confidence,
            )
        elif query_context["query_type"] == "deploy_cash":
            decision = self._build_cash_deployment(
                amount=amount,
                analysis=analysis,
                user_profile=user_profile,
                confidence=confidence,
            )
        else:
            decision = self._build_general_watch(
                analysis=analysis,
                confidence=confidence,
            )

        known_limits = []
        if not analysis.get("company_picks"):
            known_limits.append(
                "The final action is based mainly on sector and signal analysis because no company-specific picks were available."
            )
        if query_context["query_type"] == "position_review" and not query_context.get("matched_holding"):
            known_limits.append(
                "The system could not confidently match the query to a tracked holding, so the action leans on sector-level evidence."
            )
        if not analysis.get("signals_used"):
            known_limits.append(
                "No active stored signals were available, so confidence is reduced."
            )

        risk_alignment = self._risk_alignment(
            user_profile.get("risk_tolerance", "moderate"),
            decision.get("recommended_moves", []),
        )
        concentration_note = self._concentration_note(query_context.get("matched_holding"), holdings)

        review_date = (
            analysis.get("analysis", {}).get("review_date")
            or analysis.get("review_date")
            or (datetime.now(timezone.utc) + timedelta(days=21)).date().isoformat()
        )

        return {
            "recommendation_id": str(uuid.uuid4()),
            "query_type": query_context["query_type"],
            "action": decision["action"],
            "action_strength": decision["action_strength"],
            "summary": decision["summary"],
            "thesis": decision["thesis"],
            "confidence": confidence,
            "recommended_moves": decision.get("recommended_moves", []),
            "current_position": decision.get("current_position"),
            "watch_items": self._build_watch_items(analysis),
            "key_risks": analysis.get("what_could_go_wrong", [])[:5],
            "invalidation_triggers": self._build_invalidation_triggers(analysis),
            "suitability_checks": {
                "risk_profile_alignment": risk_alignment,
                "concentration": concentration_note,
                "portfolio_data_completeness": (
                    "complete" if holdings else "partial"
                ),
                "notes": self._suitability_notes(risk_alignment, concentration_note, holdings),
            },
            "evidence": {
                "signals": analysis.get("signals_used", [])[:5],
                "sectors_showing_strength": [
                    s.get("sector") for s in analysis.get("sectors_to_buy", [])[:4]
                ],
                "sectors_showing_risk": [
                    s.get("sector") for s in analysis.get("sectors_to_avoid", [])[:4]
                ],
                "macro_summary": analysis.get("global_macro_summary"),
                "root_cause_narrative": analysis.get("root_cause_narrative"),
            },
            "review_date": review_date,
            "policy_version": POLICY_VERSION,
            "known_limits": known_limits,
            "analysis": analysis,
            "disclaimer": analysis.get("disclaimer"),
        }

    def _classify_query(self, query: str, user_profile: dict) -> dict:
        normalized = _norm(query)
        holdings = user_profile.get("current_holdings_detail", [])
        matched_holding = self._match_holding(normalized, holdings)

        position_review = any(term in normalized for term in POSITION_REVIEW_TERMS)
        deploy_cash = any(term in normalized for term in DEPLOY_CASH_TERMS)

        if matched_holding and position_review:
            query_type = "position_review"
        elif position_review:
            query_type = "position_review"
        elif matched_holding and ("invest more" in normalized or "add more" in normalized):
            query_type = "position_review"
        elif deploy_cash and not matched_holding:
            query_type = "deploy_cash"
        elif matched_holding:
            query_type = "position_review"
        else:
            query_type = "general_research"

        return {
            "query_type": query_type,
            "normalized_query": normalized,
            "matched_holding": matched_holding,
            "asks_to_add": any(term in normalized for term in ("invest more", "add more", "buy more")),
            "asks_to_exit": any(term in normalized for term in ("sell", "exit", "trim")),
        }

    def _match_holding(self, normalized_query: str, holdings: list[dict]) -> dict | None:
        for holding in holdings:
            symbol = _norm(holding.get("symbol", ""))
            name = _norm(holding.get("name", ""))
            aliases = {symbol, name}
            aliases |= {part for part in name.split() if len(part) > 2}
            if any(alias and alias in normalized_query for alias in aliases):
                return holding
        return None

    def _compute_confidence(self, analysis: dict, query_context: dict) -> float:
        base = _as_float(analysis.get("confidence_score"), 0.45)
        if analysis.get("company_picks"):
            base += 0.08
        if analysis.get("signals_used"):
            base += 0.05
        if analysis.get("what_could_go_wrong"):
            base -= 0.03
        if query_context["query_type"] == "position_review" and not query_context.get("matched_holding"):
            base -= 0.12
        return round(_clamp(base), 2)

    def _build_position_review(
        self,
        *,
        query: str,
        analysis: dict,
        user_profile: dict,
        query_context: dict,
        confidence: float,
    ) -> dict:
        holding = query_context.get("matched_holding")
        if not holding:
            return {
                "action": "watch",
                "action_strength": "low",
                "summary": "The query looks like a position review, but the system could not verify the named holding in the stored portfolio.",
                "thesis": (
                    analysis.get("root_cause_narrative")
                    or analysis.get("global_macro_summary")
                    or analysis.get("narrative")
                    or "No verified holding match was available, so the platform should not force a keep, add, or exit decision."
                ),
                "recommended_moves": [{
                    "instrument": "Queried position",
                    "instrument_type": "unknown",
                    "sector": None,
                    "action": "watch",
                    "weight_pct": None,
                    "amount": None,
                    "rationale": "A tracked holding match is required before the platform can produce a position-specific action with confidence.",
                    "evidence": analysis.get("signals_used", [])[:3],
                }],
                "current_position": None,
            }

        sector_strength = {
            _norm(item.get("sector", "")): item
            for item in analysis.get("sectors_to_buy", [])
        }
        sector_risk = {
            _norm(item.get("sector", "")): item
            for item in analysis.get("sectors_to_avoid", [])
        }

        company_match = self._find_company_match(
            holding,
            analysis.get("company_picks", []),
        )

        holding_sector = _norm((holding or {}).get("sector", ""))
        positive = company_match is not None or holding_sector in sector_strength
        negative = holding_sector in sector_risk

        total_portfolio_value = _as_float(user_profile.get("portfolio_summary", {}).get("total_current_value"))
        position_value = _as_float((holding or {}).get("current_value"))
        concentration = (position_value / total_portfolio_value) if total_portfolio_value > 0 else 0.0

        action = "hold"
        strength = "medium"
        summary = "The current evidence supports holding the position while monitoring trigger conditions."

        if negative:
            action = "trim" if concentration < 0.25 else "exit"
            strength = "high" if concentration >= 0.25 and confidence >= 0.65 else "medium"
            summary = "The active signal set is turning against this position, so reducing exposure is safer than adding more."
        elif positive and query_context.get("asks_to_add") and concentration < 0.25 and confidence >= 0.65:
            action = "add"
            strength = "medium"
            summary = "The current signal set still supports the position and concentration remains within a normal range."
        elif not positive and confidence < 0.6:
            action = "watch"
            strength = "low"
            summary = "There is not enough company-specific evidence to justify adding or exiting decisively, so the position should be watched."

        thesis = (
            analysis.get("root_cause_narrative")
            or analysis.get("global_macro_summary")
            or analysis.get("narrative")
            or "The decision is driven by current sector strength, signal direction, and portfolio concentration."
        )

        instrument_name = (holding or {}).get("name") or (holding or {}).get("symbol") or "Current holding"
        rationale_parts = []
        if company_match:
            rationale_parts.append(company_match.get("signal_fit_reason", "The company still maps to a sector with active support."))
        if holding_sector in sector_strength:
            rationale_parts.append(sector_strength[holding_sector].get("reason", "The holding's sector remains in the supported set."))
        if holding_sector in sector_risk:
            rationale_parts.append(sector_risk[holding_sector].get("reason", "The holding's sector is in the risk bucket."))
        if concentration >= 0.25:
            rationale_parts.append("The position is already a large share of the portfolio, so concentration risk matters.")

        recommended_moves = [{
            "instrument": instrument_name,
            "instrument_type": (holding or {}).get("instrument_type", "stock"),
            "sector": (holding or {}).get("sector"),
            "action": action,
            "weight_pct": round(concentration * 100, 2) if concentration else None,
            "amount": None,
            "rationale": " ".join(part for part in rationale_parts if part) or summary,
            "evidence": analysis.get("signals_used", [])[:3],
        }]

        return {
            "action": action,
            "action_strength": strength,
            "summary": summary,
            "thesis": thesis,
            "recommended_moves": recommended_moves,
            "current_position": holding,
        }

    def _find_company_match(self, holding: dict | None, sector_picks: list[dict]) -> dict | None:
        if not holding:
            return None
        symbol = _norm(holding.get("symbol", ""))
        name = _norm(holding.get("name", ""))
        for sector_pick in sector_picks:
            for company in sector_pick.get("companies", []):
                if _norm(company.get("nse_symbol", "")) == symbol or _norm(company.get("name", "")) == name:
                    enriched = dict(company)
                    enriched["signal_fit_reason"] = sector_pick.get("signal_fit_reason")
                    return enriched
        return None

    def _build_cash_deployment(
        self,
        *,
        amount: float,
        analysis: dict,
        user_profile: dict,
        confidence: float,
    ) -> dict:
        if amount <= 0:
            return {
                "action": "watch",
                "action_strength": "low",
                "summary": "Fresh-capital deployment requires a valid investment amount before the platform can build a funding plan.",
                "thesis": analysis.get("global_macro_summary") or analysis.get("narrative") or "",
                "recommended_moves": [],
            }

        risk = (user_profile.get("risk_tolerance") or "moderate").lower()
        investable_ratio = {
            "conservative": 0.60,
            "moderate": 0.75,
            "aggressive": 0.90,
        }.get(risk, 0.75)

        candidates = self._build_candidates(analysis, risk)
        if not candidates:
            return {
                "action": "watch",
                "action_strength": "low",
                "summary": "The current analysis surfaced risks but not enough high-quality candidates to deploy fresh capital with confidence.",
                "thesis": analysis.get("global_macro_summary") or analysis.get("narrative") or "",
                "recommended_moves": [],
            }

        investable_amount = round(amount * investable_ratio, 2)
        reserve_amount = round(amount - investable_amount, 2)
        weighted_moves = self._allocate_candidates(candidates, investable_amount)

        if reserve_amount > 0:
            weighted_moves.append({
                "instrument": "Cash Reserve",
                "instrument_type": "cash",
                "sector": None,
                "action": "hold",
                "weight_pct": round((reserve_amount / amount) * 100, 2) if amount else 0,
                "amount": reserve_amount,
                "rationale": "A reserve is kept because the current signal set is event-driven and may change quickly.",
                "evidence": analysis.get("signals_used", [])[:2],
            })

        summary = (
            "Deploy capital in a staged way across the strongest supported ideas, while keeping a reserve because the market thesis is still event-driven."
            if reserve_amount > 0
            else "The current signal set is strong enough to deploy most of the planned capital across the highest-conviction ideas."
        )

        return {
            "action": "deploy",
            "action_strength": "high" if confidence >= 0.7 else "medium",
            "summary": summary,
            "thesis": analysis.get("root_cause_narrative") or analysis.get("global_macro_summary") or analysis.get("narrative") or "",
            "recommended_moves": weighted_moves,
        }

    def _build_candidates(self, analysis: dict, risk: str) -> list[dict]:
        candidates = []
        for sector_pick in analysis.get("company_picks", [])[:3]:
            sector = sector_pick.get("sector")
            score = _as_float(sector_pick.get("signal_fit_score"), 5.0)

            if risk == "conservative" and sector_pick.get("etf_alternative"):
                etf = sector_pick["etf_alternative"]
                candidates.append({
                    "instrument": etf.get("name"),
                    "instrument_type": "etf",
                    "sector": sector,
                    "score": score,
                    "rationale": sector_pick.get("signal_fit_reason"),
                })
                continue

            companies = [
                c for c in sector_pick.get("companies", [])
                if c.get("type") != "emerging" or risk == "aggressive"
            ]
            if companies:
                company = companies[0]
                candidates.append({
                    "instrument": company.get("name"),
                    "instrument_type": "stock",
                    "sector": sector,
                    "score": score,
                    "rationale": sector_pick.get("signal_fit_reason"),
                })
        return candidates[:3]

    def _allocate_candidates(self, candidates: list[dict], investable_amount: float) -> list[dict]:
        total_score = sum(max(_as_float(c.get("score"), 1.0), 1.0) for c in candidates)
        moves = []
        for candidate in candidates:
            score = max(_as_float(candidate.get("score"), 1.0), 1.0)
            weight_pct = round((score / total_score) * 100, 2) if total_score else 0
            amount = round((score / total_score) * investable_amount, 2) if total_score else 0
            moves.append({
                "instrument": candidate["instrument"],
                "instrument_type": candidate["instrument_type"],
                "sector": candidate.get("sector"),
                "action": "deploy",
                "weight_pct": weight_pct,
                "amount": amount,
                "rationale": candidate.get("rationale"),
                "evidence": [candidate.get("sector")],
            })
        return moves

    def _build_general_watch(self, *, analysis: dict, confidence: float) -> dict:
        return {
            "action": "watch" if confidence < 0.65 else "hold",
            "action_strength": "low" if confidence < 0.65 else "medium",
            "summary": "The analysis is useful for monitoring, but the query does not yet map cleanly to a deploy-or-exit decision.",
            "thesis": analysis.get("global_macro_summary") or analysis.get("narrative") or "",
            "recommended_moves": [],
        }

    def _risk_alignment(self, risk_profile: str, moves: list[dict]) -> str:
        risk_profile = (risk_profile or "moderate").lower()
        contains_stock = any(move.get("instrument_type") == "stock" for move in moves)
        contains_emerging = any("emerging" in _norm(move.get("rationale", "")) for move in moves)
        if risk_profile == "conservative" and (contains_stock or contains_emerging):
            return "caution"
        return "aligned"

    def _concentration_note(self, matched_holding: dict | None, holdings: list[dict]) -> str:
        if matched_holding:
            weight = _as_float(matched_holding.get("weight_pct"))
            if weight >= 25:
                return "high"
            if weight >= 15:
                return "moderate"
            return "normal"
        if not holdings:
            return "unknown"
        return "normal"

    def _suitability_notes(self, risk_alignment: str, concentration: str, holdings: list[dict]) -> list[str]:
        notes = []
        if risk_alignment == "caution":
            notes.append("The proposed moves are more volatile than a conservative profile would normally allow.")
        if concentration == "high":
            notes.append("The current position is a high concentration holding and should not automatically be increased.")
        if not holdings:
            notes.append("No stored portfolio was found, so concentration and overlap checks are limited.")
        return notes

    def _build_watch_items(self, analysis: dict) -> list[dict]:
        items = []
        for trigger in analysis.get("rebalancing_triggers", [])[:5]:
            items.append({
                "trigger": trigger.get("condition") or trigger.get("at"),
                "implication": trigger.get("implication") or trigger.get("action"),
            })
        if not items:
            for timeline in analysis.get("event_timelines", [])[:3]:
                items.append({
                    "trigger": timeline.get("signal_title"),
                    "implication": (
                        timeline.get("tomorrow_prediction", {}) or {}
                    ).get("summary"),
                })
        return items

    def _build_invalidation_triggers(self, analysis: dict) -> list[str]:
        triggers = []
        for risk in analysis.get("what_could_go_wrong", [])[:3]:
            triggers.append(risk)
        for trigger in analysis.get("rebalancing_triggers", [])[:2]:
            if trigger.get("condition"):
                triggers.append(trigger["condition"])
        return triggers
