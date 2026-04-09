"""
Credibility Scoring Engine — Separates garbage from gold.

Every signal gets scored on three axes:
1. SOURCE_SCORE — How trustworthy is the source? (hardcoded lookup)
2. CLAIM_WEIGHT — Is this fact, analysis, opinion, or a tip? (LLM classifies)
3. CORROBORATION — How many independent sources report the same thing?

Final credibility = min(source_score * claim_weight * corroboration_multiplier, 1.0)
Threshold: Only signals with credibility >= 0.5 enter the pipeline.
"""
import structlog
from difflib import SequenceMatcher

logger = structlog.get_logger()

# Source scores — based on editorial standards, regulatory status
SOURCE_SCORES = {
    # Tier 1: Government/Regulatory
    "US Federal Reserve": 0.95, "European Central Bank": 0.95,
    "RBI": 0.95, "SEBI": 0.95, "Ministry of Finance": 0.95,
    "IMF": 0.95, "World Bank": 0.95, "OPEC": 0.95,
    "FRED": 0.95, "BSE Announcements": 0.95, "RBI Data": 0.95,
    "PIB": 0.95, "NSE FII/DII": 0.95,
    # Tier 2: Major wire services + established financial media
    "Reuters Business": 0.85, "Reuters Top News": 0.85,
    "BBC Business": 0.85, "NYT Business": 0.85, "Wall Street Journal": 0.85,
    "Economic Times Markets": 0.75, "Economic Times Economy": 0.75,
    "Mint Markets": 0.75, "Mint Economy": 0.75,
    "Business Standard": 0.75, "Moneycontrol": 0.75, "Financial Express": 0.75,
    # Tier 3: Specialized/regional
    "OilPrice.com": 0.60, "Mining.com": 0.60, "SCMP China Business": 0.60,
    "Japan News": 0.60, "Arabian Business": 0.60, "Hindu BusinessLine": 0.65,
    # Silver: Aggregators
    "Google News": 0.40,
}

TIER_FALLBACK_SCORES = {1: 0.95, 2: 0.75, 3: 0.60, 4: 0.30}

CLAIM_WEIGHTS = {
    "factual": 1.0,   # Verifiable fact
    "analysis": 0.7,  # Informed reasoning
    "opinion": 0.4,   # Subjective view
    "tip": 0.0,       # REJECTED
}

CREDIBILITY_THRESHOLD = 0.5


class CredibilityEngine:
    def get_source_score(self, source_name: str, tier: int = 3) -> float:
        if source_name in SOURCE_SCORES:
            return SOURCE_SCORES[source_name]
        return TIER_FALLBACK_SCORES.get(tier, 0.30)

    def get_claim_weight(self, claim_type: str) -> float:
        return CLAIM_WEIGHTS.get(claim_type, CLAIM_WEIGHTS["analysis"])

    def get_corroboration_multiplier(self, corroboration_count: int) -> float:
        if corroboration_count >= 3:
            return 1.3
        elif corroboration_count == 2:
            return 1.1
        else:
            return 0.8

    def compute_credibility(self, source_name: str, tier: int, claim_type: str, corroboration_count: int = 1) -> float:
        source_score = self.get_source_score(source_name, tier)
        claim_weight = self.get_claim_weight(claim_type)
        corroboration = self.get_corroboration_multiplier(corroboration_count)
        raw = source_score * claim_weight * corroboration
        return round(min(raw, 1.0), 2)

    def passes_threshold(self, credibility_score: float) -> bool:
        return credibility_score >= CREDIBILITY_THRESHOLD

    def find_corroborating_signals(self, title: str, entities: list, existing_signals: list, similarity_threshold: float = 0.55) -> list:
        matches = []
        title_lower = title.lower()
        entities_set = set(e.lower() for e in (entities or []))
        for signal in existing_signals:
            sig_title = (signal.get("title") or "").lower()
            sig_entities = set(e.lower() for e in (signal.get("entities_mentioned") or []))
            entity_overlap = len(entities_set & sig_entities)
            title_sim = SequenceMatcher(None, title_lower, sig_title).ratio()
            if entity_overlap >= 2 or title_sim >= similarity_threshold:
                matches.append(signal.get("id"))
        return matches
