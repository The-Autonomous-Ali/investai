"""
Orchestrator Agent — The master coordinator.
Receives user queries, builds a task plan, dispatches to specialist agents,
assembles the final output, and passes it through the Critic.
"""
import asyncio
import time
import structlog
import os
import json
from typing import Any
import google.generativeai as genai
from anthropic import AsyncAnthropic

from .signal_watcher import SignalWatcherAgent
from .research_agent import ResearchAgent
from .agents_impl import PatternMatcherAgent, PortfolioAgent, TaxAgent, MemoryAgent, CriticAgent, WatchdogAgent, TemporalAgent
from .company_intelligence import CompanyIntelligenceAgent, InvestmentManagerAgent

logger = structlog.get_logger()

def get_anthropic_client():
    return AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def get_gemini_model(model_name=None):
    model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    return genai.GenerativeModel(model_name=model_name)

ORCHESTRATOR_PROMPT = """You are the Orchestrator of InvestAI, a financial intelligence system for global markets.

A user from {country} has submitted a query. Your job is to:
1. Understand the intent
2. Build an ordered task plan
3. Identify which agents are needed

Available agents:
- signal_watcher: Gets current top market signals
- research_agent: Deep-dives a signal for {country}-specific impacts
- pattern_matcher: Finds historical analogues for current events
- portfolio_agent: Builds specific allocation plan
- tax_agent: Optimizes allocation for {country} tax efficiency
- memory_agent: Retrieves/stores user history
- temporal_agent: Assesses event lifecycle and time horizon

User query: {query}
User profile summary: {user_profile}
Investment amount: {amount}
Time horizon: {horizon}
Country: {country}

Return a JSON task plan:
{{
  "intent": "what the user is asking for",
  "task_plan": [
    {{"step": 1, "agent": "agent_name", "input": "what to give this agent", "depends_on": []}},
    ...
  ],
  "requires_real_time_signals": true/false,
  "urgency": "high/medium/low"
}}
"""


class OrchestratorAgent:
    def __init__(self, db_session, redis_client, neo4j_driver):
        self.db       = db_session
        self.redis    = redis_client
        self.neo4j    = neo4j_driver
        self.watchdog = WatchdogAgent()

        # Instantiate all specialist agents
        self.agents = {
            "signal_watcher":         SignalWatcherAgent(db_session, redis_client),
            "research_agent":         ResearchAgent(db_session, neo4j_driver),
            "pattern_matcher":        PatternMatcherAgent(db_session),
            "portfolio_agent":        PortfolioAgent(db_session),
            "tax_agent":              TaxAgent(),
            "memory_agent":           MemoryAgent(db_session),
            "critic_agent":           CriticAgent(),
            "temporal_agent":         TemporalAgent(db_session),
            "company_intelligence":   CompanyIntelligenceAgent(db_session),
            "investment_manager":     InvestmentManagerAgent(db_session),
        }

    async def run(self, user_id: str, query: str, amount: float, horizon: str, country: str = "India") -> dict:
        """Main entry point. Orchestrates all agents to answer user query."""
        start_time = time.time()
        log = logger.bind(user_id=user_id, query=query[:50])
        log.info("orchestrator.start")

        # Shared state object — travels through all agents
        state = {
            "user_id": user_id,
            "query": query,
            "amount": amount,
            "horizon": horizon,
            "country": country,
            "agent_outputs": {},
            "agent_logs": {},
            "conflicts": [],
            "final_recommendation": None,
        }

        try:
            # Step 1: Get user memory and profile
            memory_output = await self.agents["memory_agent"].get_user_context(user_id)
            state["user_profile"] = memory_output
            state["agent_outputs"]["memory_agent"] = memory_output

            # Step 2: Ask Orchestrator LLM to build task plan
            task_plan = await self._build_task_plan(state)
            log.info("orchestrator.task_plan", steps=len(task_plan["task_plan"]))

            # Step 3: Execute tasks in order, respecting dependencies
            await self._execute_task_plan(state, task_plan)

            # Step 4: Watchdog checks all outputs for conflicts
            conflicts = await self.watchdog.check(state["agent_outputs"])
            state["conflicts"] = conflicts
            if conflicts:
                log.warning("orchestrator.conflicts_detected", count=len(conflicts))

            # Step 5: Critic reviews the portfolio recommendation
            portfolio_output = state["agent_outputs"].get("portfolio_agent", {})
            tax_output       = state["agent_outputs"].get("tax_agent", {})

            critic_result = await self.agents["critic_agent"].review({
                "portfolio": portfolio_output,
                "tax":       tax_output,
                "signals":   state["agent_outputs"].get("signal_watcher", {}),
                "research":  state["agent_outputs"].get("research_agent", {}),
                "patterns":  state["agent_outputs"].get("pattern_matcher", {}),
                "user_profile": state["user_profile"],
                "conflicts": conflicts,
            })

            # If critic says REVISE, loop back to portfolio agent once
            if critic_result["verdict"] == "REVISE":
                log.info("orchestrator.critic_revise")
                portfolio_output = await self.agents["portfolio_agent"].run({
                    **state["agent_outputs"],
                    "critic_feedback": critic_result["feedback"],
                    "user_profile": state["user_profile"],
                    "amount": amount,
                    "horizon": horizon,
                })
                state["agent_outputs"]["portfolio_agent"] = portfolio_output
                # Run critic once more
                critic_result = await self.agents["critic_agent"].review({
                    "portfolio": portfolio_output,
                    **{k: v for k, v in critic_result.items() if k != "portfolio"},
                })

            # Step 6: Assemble final output
            final = await self._assemble_final_output(state, critic_result)
            state["final_recommendation"] = final

            # Step 7: Store advice in memory
            await self.agents["memory_agent"].store_advice(user_id, {
                "query":          query,
                "recommendation": final,
                "signals_used":   state["agent_outputs"].get("signal_watcher", {}).get("signals", []),
                "market_snapshot": state["agent_outputs"].get("signal_watcher", {}).get("market_snapshot", {}),
                "critic_verdict": critic_result["verdict"],
            })

            elapsed = round(time.time() - start_time, 2)
            log.info("orchestrator.complete", elapsed_s=elapsed)

            return {
                "success": True,
                "recommendation": final,
                "meta": {
                    "elapsed_seconds": elapsed,
                    "agents_used": list(state["agent_outputs"].keys()),
                    "conflicts_detected": len(conflicts),
                    "critic_verdict": critic_result["verdict"],
                    "confidence_score": final.get("confidence_score", 0),
                }
            }

        except Exception as e:
            log.error("orchestrator.error", error=str(e))
            return {"success": False, "error": str(e)}

    async def _build_task_plan(self, state: dict) -> dict:
        """Ask the LLM to build an ordered task plan for this query."""
        profile_summary = self._summarize_profile(state["user_profile"])
        prompt = ORCHESTRATOR_PROMPT.format(
            query=state["query"],
            user_profile=profile_summary,
            amount=state["amount"],
            horizon=state["horizon"],
            country=state["country"],
        )

        provider = os.getenv("AI_PROVIDER", "gemini")

        if provider == "anthropic":
            client = get_anthropic_client()
            response = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
        else:
            model = get_gemini_model()
            response = await model.generate_content_async(prompt)
            text = response.text

        # Strip markdown if present
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    async def _execute_task_plan(self, state: dict, task_plan: dict):
        """Execute tasks, running independent tasks in parallel."""
        tasks = task_plan["task_plan"]
        completed = set()

        while len(completed) < len(tasks):
            # Find tasks whose dependencies are all satisfied
            ready = [
                t for t in tasks
                if t["step"] not in completed
                and all(dep in completed for dep in t.get("depends_on", []))
            ]

            if not ready:
                break  # avoid infinite loop on bad task plan

            # Run ready tasks in parallel
            await asyncio.gather(*[
                self._run_single_task(state, task)
                for task in ready
            ])

            for task in ready:
                completed.add(task["step"])

    async def _run_single_task(self, state: dict, task: dict):
        """Run a single agent task and store the result in shared state."""
        agent_name = task["agent"]
        agent = self.agents.get(agent_name)
        if not agent:
            return

        start = time.time()
        log = logger.bind(agent=agent_name)

        try:
            log.info("agent.start")

            # Build input from state
            agent_input = {
                "task_input":   task.get("input", ""),
                "user_profile": state["user_profile"],
                "amount":       state["amount"],
                "horizon":      state["horizon"],
                "country":      state["country"],
                "query":        state["query"],
                **state["agent_outputs"],   # pass all previous outputs
            }

            # Route to correct agent method
            if agent_name == "signal_watcher":
                result = await agent.get_current_signals()
            elif agent_name == "research_agent":
                signals = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                result  = await agent.analyze(signals, state["country"])
            elif agent_name == "pattern_matcher":
                signals = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                result  = await agent.find_patterns(signals, state["country"])
            elif agent_name == "portfolio_agent":
                result  = await agent.run(agent_input)
            elif agent_name == "tax_agent":
                portfolio = state["agent_outputs"].get("portfolio_agent", {})
                result    = await agent.optimize(portfolio, state["user_profile"], state["country"])
            elif agent_name == "temporal_agent":
                signals = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                result  = await agent.assess_timelines(signals)
            elif agent_name == "company_intelligence":
                research = state["agent_outputs"].get("research_agent", {})
                result   = await agent.analyze({
                    **agent_input,
                    "sectors_to_buy":   research.get("sectors_analysis", {}).get("strong_buy", []) +
                                        research.get("sectors_analysis", {}).get("buy", []),
                    "sectors_to_avoid": research.get("sectors_analysis", {}).get("avoid", []) +
                                        research.get("sectors_analysis", {}).get("strong_avoid", []),
                })
            elif agent_name == "investment_manager":
                result = await agent.build_strategy({
                    **state["agent_outputs"],
                    "user_profile": state["user_profile"],
                    "amount":       state["amount"],
                    "horizon":      state["horizon"],
                })
            else:
                result = {}

            state["agent_outputs"][agent_name] = result
            elapsed_ms = round((time.time() - start) * 1000)
            log.info("agent.complete", elapsed_ms=elapsed_ms)

        except asyncio.TimeoutError:
            log.warning("agent.timeout")
            state["agent_outputs"][agent_name] = {"error": "timeout", "used_cache": True}
        except Exception as e:
            log.error("agent.error", error=str(e))
            state["agent_outputs"][agent_name] = {"error": str(e)}

    async def _assemble_final_output(self, state: dict, critic_result: dict) -> dict:
        """Combine all agent outputs into the final user-facing recommendation."""
        portfolio = state["agent_outputs"].get("portfolio_agent", {})
        tax       = state["agent_outputs"].get("tax_agent", {})
        temporal  = state["agent_outputs"].get("temporal_agent", {})
        research  = state["agent_outputs"].get("research_agent", {})
        patterns  = state["agent_outputs"].get("pattern_matcher", {})
        signals   = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])

        return {
            "allocation":             portfolio.get("allocation", {}),
            "sectors_to_buy":         portfolio.get("sectors_to_buy", []),
            "sectors_to_avoid":       portfolio.get("sectors_to_avoid", []),
            "rebalancing_triggers":   portfolio.get("rebalancing_triggers", []),
            "tax_optimizations":      tax.get("optimizations", []),
            "post_tax_return_estimate": tax.get("post_tax_return_estimate"),
            "narrative":              portfolio.get("narrative", ""),
            "reasoning_chain":        research.get("impact_chain", []),
            "event_timelines":        temporal.get("timelines", []),
            "historical_precedents":  patterns.get("best_analogues", []),
            "confidence_score":       portfolio.get("confidence_score", 0.5),
            "what_could_go_wrong":    critic_result.get("risks", []),
            "signals_used":           [s.get("title") for s in signals[:5]],
            "review_date":            temporal.get("recommended_review_date"),

            # ── NEW: Company-level picks ──────────────────────────────────────
            "company_picks":          state["agent_outputs"].get("company_intelligence", {}).get("sector_picks", []),
            "portfolio_construction_note": state["agent_outputs"].get("company_intelligence", {}).get("portfolio_construction_note", ""),

            # ── NEW: Full investment strategy ─────────────────────────────────
            "investment_strategy":    state["agent_outputs"].get("investment_manager", {}),

            "disclaimer": (
                "This analysis is for educational purposes only and does not constitute "
                "SEBI-registered investment advice. Please consult a qualified financial "
                "advisor before making investment decisions."
            ),
        }

    def _summarize_profile(self, profile: dict) -> str:
        if not profile:
            return "New user, no history"
        return (
            f"Risk: {profile.get('risk_tolerance', 'moderate')}, "
            f"Experience: {profile.get('experience_level', 'intermediate')}, "
            f"Tax bracket: {profile.get('tax_bracket', 30)}%, "
            f"Past advice count: {len(profile.get('past_advice', []))}"
        )
