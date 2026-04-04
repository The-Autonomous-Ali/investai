"""
Adversarial Agent — The Bull vs. Bear Debate Protocol.
Ensures no stock enters the portfolio without surviving a stress test.
"""
import json
import structlog
from utils.llm_client import call_llm

logger = structlog.get_logger()

ADVERSARIAL_PROMPT = """You are an Institutional Investment Committee consisting of a Bull (optimist) and a Bear (pessimist).
You are evaluating a proposed stock pick for an Indian retail investor.

COMPANY: {company_name} ({symbol})
PROPOSED ALLOCATION: {allocation}%
MACRO ENVIRONMENT: {macro_context}

Step 1 (The Bear): Attack this stock pick. Focus on valuation, macro headwinds, sector risks, or corporate governance. Be brutal but factual.
Step 2 (The Bull): Defend the stock. Focus on growth catalysts, undervalued assets, or strong technicals.
Step 3 (The Verdict): Based purely on risk/reward, decide if the stock stays in the portfolio, gets its allocation reduced, or is rejected entirely.

Return ONLY valid JSON:
{{
  "bear_thesis": "...",
  "bull_thesis": "...",
  "verdict": "APPROVE | REDUCE | REJECT",
  "recommended_allocation": <number>,
  "reasoning": "..."
}}
"""

class AdversarialAgent:
    def __init__(self):
        pass

    async def debate_picks(self, company_picks: list, macro_context: dict) -> list:
        log = logger.bind(picks_count=len(company_picks))
        log.info("adversarial_debate.start")
        
        surviving_picks = []
        
        for pick in company_picks:
            symbol = pick.get("nse_symbol")
            
            prompt = ADVERSARIAL_PROMPT.format(
                company_name=pick.get("name"),
                symbol=symbol,
                allocation=pick.get("proposed_weight", 5), # Assume 5% default
                macro_context=json.dumps(macro_context)
            )
            
            # Using a fast, reasoning-heavy model like Llama 3 or DeepSeek
            response = await call_llm(prompt, agent_name="adversarial_agent")
            debate_result = json.loads(response)
            
            pick["debate"] = debate_result
            
            if debate_result["verdict"] in ["APPROVE", "REDUCE"]:
                pick["final_weight"] = debate_result["recommended_allocation"]
                surviving_picks.append(pick)
            else:
                log.warning(f"Stock {symbol} rejected by Bear Agent.")
                
        log.info("adversarial_debate.complete", survived=len(surviving_picks))
        return surviving_picks