"""
Adversarial Agent — The Bull vs. Bear Analysis Protocol.
Provides balanced analysis of both sides for every company, so the user
can weigh the arguments and make their own decision.
SEBI Option 1: No verdicts, no allocation recommendations.
"""
import json
import structlog
from utils.llm_client import call_llm

logger = structlog.get_logger()

ADVERSARIAL_PROMPT = """You are an Institutional Research Team presenting BOTH sides of the argument for a stock.
You are NOT making a buy/sell decision. You are giving the investor balanced analysis so THEY can decide.

COMPANY: {company_name} ({symbol})
MACRO ENVIRONMENT: {macro_context}
LIVE DATA (if available): {live_data}

Step 1 (The Bear Case): Present the strongest factual argument AGAINST this company right now.
Focus on: valuation concerns, macro headwinds, sector risks, corporate governance, competitive threats.
Be brutally honest but factual — cite data where available.

Step 2 (The Bull Case): Present the strongest factual argument FOR this company right now.
Focus on: growth catalysts, undervalued aspects, strong fundamentals, sector tailwinds, management quality.
Be specific and cite data where available.

Step 3 (Key Debate Point): What is the SINGLE most important question the investor should answer
before making any decision about this stock?

IMPORTANT: Do NOT provide a verdict (buy/sell/hold). Do NOT recommend an allocation percentage.
Your job is to present both sides clearly so the investor can make their own informed decision.

Return ONLY valid JSON:
{{
  "bull_case": {{
    "thesis": "2-3 sentence bull thesis",
    "supporting_evidence": ["Evidence point 1", "Evidence point 2"],
    "catalysts": ["Near-term catalyst 1", "Near-term catalyst 2"],
    "strength": 7
  }},
  "bear_case": {{
    "thesis": "2-3 sentence bear thesis",
    "supporting_evidence": ["Evidence point 1", "Evidence point 2"],
    "risks": ["Key risk 1", "Key risk 2"],
    "strength": 5
  }},
  "key_debate_point": "The single most important question the investor should answer",
  "data_gaps": ["What information is missing that would strengthen the analysis"],
  "factors_to_monitor": ["What the investor should watch going forward"]
}}
"""


class AdversarialAgent:
    def __init__(self):
        pass

    async def debate_picks(self, company_picks: list, macro_context: dict) -> list:
        log = logger.bind(picks_count=len(company_picks))
        log.info("adversarial_analysis.start")

        analyzed_picks = []

        for pick in company_picks:
            symbol = pick.get("nse_symbol")

            prompt = ADVERSARIAL_PROMPT.format(
                company_name=pick.get("name"),
                symbol=symbol,
                macro_context=json.dumps(macro_context)[:1000],
                live_data=json.dumps(pick.get("live_data") or pick.get("data_highlights") or {})[:500],
            )

            try:
                response = await call_llm(prompt, agent_name="adversarial_agent")
                debate_result = json.loads(response)
                pick["debate"] = debate_result
            except Exception as e:
                log.warning("adversarial_analysis.failed", symbol=symbol, error=str(e))
                pick["debate"] = {
                    "bull_case": {"thesis": "Analysis unavailable", "strength": 0},
                    "bear_case": {"thesis": "Analysis unavailable", "strength": 0},
                    "key_debate_point": "Unable to generate analysis for this company",
                }

            analyzed_picks.append(pick)

        log.info("adversarial_analysis.complete", analyzed=len(analyzed_picks))
        return analyzed_picks
