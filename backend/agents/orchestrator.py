"""
Orchestrator Agent — The master coordinator.
UPDATED: Added Quant Risk Engine + Live Data Scrapers (FII/DII + Max Pain).
"""
import asyncio
import time
import structlog
import json

from .signal_watcher import SignalWatcherAgent
from .research_agent import ResearchAgent
from .agents_impl import (
    PatternMatcherAgent, PortfolioAgent, TaxAgent,
    MemoryAgent, CriticAgent, WatchdogAgent, TemporalAgent
)
from .company_intelligence import CompanyIntelligenceAgent, InvestmentManagerAgent
from .global_macro_agent import GlobalMacroAgent
from .sentiment_aggregator_agent import SentimentAggregatorAgent
from .candlestick_engine import TechnicalAnalysisAgent
from .plain_language_formatter import PlainLanguageFormatter
from .market_intelligence import MarketIntelligence
from .adversarial_agent import AdversarialAgent
from .risk_engine import RiskEngine
from .data_scrapers import NSEDataScraper
from utils.llm_client import call_llm, call_llm_structured
from pydantic import BaseModel, ConfigDict

logger = structlog.get_logger()


class _TaskPlanSchema(BaseModel):
    """Loose schema — just verifies the LLM returned a task_plan list."""
    model_config = ConfigDict(extra="allow")
    task_plan: list[dict]

ORCHESTRATOR_PROMPT = """You are the Orchestrator of InvestAI, a financial intelligence system for global markets.

A user from {country} has submitted a query. Your job is to:
1. Understand the intent
2. Build an ordered task plan
3. Identify which agents are needed

Available agents:
- signal_watcher: Gets current top market signals (global + India)
- global_macro_agent: Scores global signals for India impact — run BEFORE research
- research_agent: Deep-dives signals for {country}-specific impacts
- pattern_matcher: Finds historical analogues for current events
- portfolio_agent: Builds specific allocation plan
- tax_agent: Optimizes allocation for {country} tax efficiency
- memory_agent: Retrieves/stores user history
- temporal_agent: Assesses event lifecycle and time horizon
- company_intelligence: Finds best companies in target sectors
- adversarial_agent: Subjects company picks to a Bull vs. Bear debate to stress-test the thesis
- sentiment_aggregator: Scores market sentiment for identified companies

User query: {query}
User profile summary: {user_profile}
Investment amount: {amount}
Time horizon: {horizon}
Country: {country}

Return a JSON task plan. Always include global_macro_agent after signal_watcher.
Always include sentiment_aggregator after company_intelligence.

{{
  "intent": "what the user is asking for",
  "task_plan": [
    {{"step": 1, "agent": "signal_watcher",      "input": "get current global + India signals", "depends_on": []}},
    {{"step": 2, "agent": "global_macro_agent",  "input": "score global signal India impact",   "depends_on": [1]}},
    {{"step": 3, "agent": "research_agent",      "input": "deep analysis with macro context",   "depends_on": [2]}},
    {{"step": 4, "agent": "pattern_matcher",     "input": "historical analogues",               "depends_on": [2]}},
    {{"step": 5, "agent": "temporal_agent",      "input": "event lifecycles",                   "depends_on": [2]}},
    {{"step": 6, "agent": "portfolio_agent",     "input": "build allocation",                   "depends_on": [3, 4]}},
    {{"step": 7, "agent": "tax_agent",           "input": "optimize for tax",                   "depends_on": [6]}},
    {{"step": 8, "agent": "company_intelligence","input": "find best companies",                "depends_on": [3]}},
    {{"step": 9, "agent": "adversarial_agent",   "input": "stress test company picks",          "depends_on": [8]}},
    {{"step": 10,"agent": "sentiment_aggregator","input": "score company sentiments",           "depends_on": [9]}},
    {{"step": 11,"agent": "investment_manager",  "input": "build full playbook",                "depends_on": [6, 7, 9, 10]}}
  ],
  "requires_real_time_signals": true,
  "urgency": "high/medium/low"
}}
"""


class OrchestratorAgent:
    def __init__(self, db_session, redis_client, neo4j_driver):
        self.db       = db_session
        self.redis    = redis_client
        self.neo4j    = neo4j_driver
        self.watchdog = WatchdogAgent()

        # ── Specialist Agents ──────────────────────────────────────────────────
        self.agents = {
            "signal_watcher":        SignalWatcherAgent(db_session, redis_client),
            "global_macro_agent":    GlobalMacroAgent(db_session, redis_client),
            "research_agent":        ResearchAgent(db_session, neo4j_driver),
            "pattern_matcher":       PatternMatcherAgent(db_session),
            "portfolio_agent":       PortfolioAgent(db_session),
            "tax_agent":             TaxAgent(),
            "memory_agent":          MemoryAgent(db_session),
            "critic_agent":          CriticAgent(),
            "temporal_agent":        TemporalAgent(db_session),
            "company_intelligence":  CompanyIntelligenceAgent(db_session),
            "adversarial_agent":     AdversarialAgent(),
            "sentiment_aggregator":  SentimentAggregatorAgent(db_session, redis_client),
            "investment_manager":    InvestmentManagerAgent(db_session),
        }

        # ── Post-Pipeline Processors ───────────────────────────────────────────
        self.technical_agent  = TechnicalAnalysisAgent()
        self.plain_formatter  = PlainLanguageFormatter()
        self.market_intel     = MarketIntelligence()
        self.risk_engine      = RiskEngine()
        self.live_scraper     = NSEDataScraper()

    async def run(
        self,
        user_id: str,
        query: str,
        amount: float,
        horizon: str,
        country: str = "India"
    ) -> dict:
        """Main entry point. Orchestrates all agents to answer user query."""
        start_time = time.time()
        log = logger.bind(user_id=user_id, query=query[:50])
        log.info("orchestrator.start")

        state = {
            "user_id":              user_id,
            "query":                query,
            "amount":               amount,
            "horizon":              horizon,
            "country":              country,
            "agent_outputs":        {},
            "agent_logs":           {},
            "conflicts":            [],
            "final_recommendation": None,
            "live_market_data":     {}
        }

        try:
            # ── Step 0: Fetch Live Institutional Flows (FII/DII) ───────────────
            log.info("orchestrator.fetching_fii_dii")
            try:
                state["live_market_data"]["fii_dii_flows"] = await self.live_scraper.fetch_fii_dii_flows()
            except Exception as e:
                log.warning("orchestrator.fii_dii_failed", error=str(e))

            # ── Step 1: User memory ────────────────────────────────────────────
            memory_output = await self.agents["memory_agent"].get_user_context(user_id)
            state["user_profile"] = memory_output
            state["agent_outputs"]["memory_agent"] = memory_output

            # ── Step 2: Build task plan ────────────────────────────────────────
            task_plan = await self._build_task_plan(state)
            log.info("orchestrator.task_plan", steps=len(task_plan["task_plan"]))

            # ── Step 3: Execute all agents in pipeline ──────────────────────
            await self._execute_task_plan(state, task_plan)

            # ── Step 3.5: Assemble causal chain from available agent outputs ──
            try:
                signals_list = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                research_out = state["agent_outputs"].get("research_agent", {})
                temporal_out = state["agent_outputs"].get("temporal_agent", {})
                # Use first signal as representative for root cause chain
                signal_data = signals_list[0] if signals_list else {}
                causal_chain = ResearchAgent.assemble_full_chain(
                    signal_data, research_out, temporal_out
                )
                state["agent_outputs"]["causal_chain"] = causal_chain
                log.info("orchestrator.causal_chain_assembled",
                         root_causes=len(causal_chain.get("root_causes", [])),
                         forward_steps=len(causal_chain.get("forward_chain", [])))
            except Exception as e:
                log.warning("orchestrator.causal_chain_failed", error=str(e))
                state["agent_outputs"]["causal_chain"] = {}

            # ── Step 4: Watchdog conflict check ───────────────────────────────
            conflicts = await self.watchdog.check(state["agent_outputs"])
            state["conflicts"] = conflicts
            if conflicts:
                log.warning("orchestrator.conflicts_detected", count=len(conflicts))

            # ── Step 5: Critic review ──────────────────────────────────────────
            portfolio_output = state["agent_outputs"].get("portfolio_agent", {})
            tax_output       = state["agent_outputs"].get("tax_agent", {})

            degraded_pre_critic = [
                name for name, out in state["agent_outputs"].items()
                if isinstance(out, dict) and "error" in out
            ]

            critic_result = await self.agents["critic_agent"].review({
                "portfolio":    portfolio_output,
                "tax":          tax_output,
                "signals":      state["agent_outputs"].get("signal_watcher", {}),
                "research":     state["agent_outputs"].get("research_agent", {}),
                "patterns":     state["agent_outputs"].get("pattern_matcher", {}),
                "macro":        state["agent_outputs"].get("global_macro_agent", {}),
                "sentiment":    state["agent_outputs"].get("sentiment_aggregator", {}),
                "user_profile": state["user_profile"],
                "conflicts":    conflicts,
            })

            # Partial data → downgrade REJECT to PASS with low confidence
            if critic_result.get("verdict") == "REJECT" and degraded_pre_critic:
                log.warning("orchestrator.critic_reject_overridden_partial_data",
                            degraded=degraded_pre_critic)
                critic_result["verdict"] = "PASS"
                critic_result["confidence"] = "low"
                critic_result.setdefault("risks", []).append(
                    f"Partial data: {len(degraded_pre_critic)} agent(s) degraded "
                    f"({', '.join(degraded_pre_critic[:3])})"
                )

            if critic_result.get("verdict") == "REVISE":
                log.info("orchestrator.critic_revise")
                portfolio_output = await self.agents["portfolio_agent"].run({
                    **state["agent_outputs"],
                    "critic_feedback": critic_result.get("feedback", ""),
                    "user_profile":    state["user_profile"],
                    "amount":          amount,
                    "horizon":         horizon,
                })
                state["agent_outputs"]["portfolio_agent"] = portfolio_output
                critic_result = await self.agents["critic_agent"].review({
                    "portfolio": portfolio_output,
                    **{k: v for k, v in critic_result.items() if k != "portfolio"},
                })

            # ── Step 6: Get India VIX for downstream modules ───────────────────
            india_vix_raw = (
                state["agent_outputs"]
                .get("signal_watcher", {})
                .get("market_snapshot", {})
                .get("india_vix", {})
            )
            india_vix = india_vix_raw.get("value", 17.0) if isinstance(india_vix_raw, dict) else 17.0

            # ── Step 7: Market Intelligence & Live Max Pain ────────────────────
            log.info("orchestrator.market_intelligence_start")
            try:
                symbols = [
                    c.get("nse_symbol", "")
                    for sector in state["agent_outputs"]
                        .get("company_intelligence", {})
                        .get("sector_picks", [])
                    for c in sector.get("companies", [])
                    if c.get("nse_symbol")
                ]
                
                market_intel = await self.market_intel.get_full_intelligence(
                    symbols=symbols[:3],
                    macro_snapshot=state["agent_outputs"].get("signal_watcher", {}).get("market_snapshot", {}),
                    signals=state["agent_outputs"].get("signal_watcher", {}).get("signals", []),
                    india_vix=india_vix,
                    risk_regime=state["agent_outputs"].get("global_macro_agent", {}).get("risk_regime", "neutral"),
                )

                # Fetch LIVE Max Pain for the top picked stocks
                live_max_pain_data = {}
                for symbol in symbols[:3]:
                    pain_result = await self.live_scraper.calculate_max_pain(symbol)
                    if "error" not in pain_result:
                        live_max_pain_data[symbol] = pain_result
                
                market_intel["max_pain"] = live_max_pain_data
                
                state["agent_outputs"]["market_intelligence"] = market_intel
                log.info("orchestrator.market_intelligence_complete")
            except Exception as e:
                log.warning("orchestrator.market_intelligence_failed", error=str(e))
                state["agent_outputs"]["market_intelligence"] = {}

            # ── Step 8: Technical Analysis ─────────────────────────────────────
            log.info("orchestrator.technical_analysis_start")
            technical_results = []
            try:
                company_picks = state["agent_outputs"].get("company_intelligence", {})
                all_stocks    = []
                for sector_pick in company_picks.get("sector_picks", []):
                    all_stocks.extend(sector_pick.get("companies", []))

                if all_stocks:
                    technical_results = await self.technical_agent.analyze_batch(
                        stocks=all_stocks[:6],
                        investment_amount=amount,
                        india_vix=india_vix,
                    )
            except Exception as e:
                log.warning("orchestrator.technical_analysis_failed", error=str(e))

            state["agent_outputs"]["technical_analysis"] = technical_results

            # ── Step 8.5: Quantitative Risk Engine ─────────────────────────────
            log.info("orchestrator.risk_engine_start")
            quant_risk = {}
            try:
                surviving_picks = state["agent_outputs"].get("adversarial_agent", {}).get("surviving_picks", [])
                if surviving_picks:
                    quant_risk = await self.risk_engine.calculate_portfolio_risk(
                        surviving_picks=surviving_picks,
                        total_amount=amount
                    )
                state["agent_outputs"]["quant_risk"] = quant_risk
            except Exception as e:
                log.warning("orchestrator.risk_engine_failed", error=str(e))
                state["agent_outputs"]["quant_risk"] = {}

            # ── Step 9: Assemble final output ──────────────────────────────────
            final = await self._assemble_final_output(
                state, critic_result, technical_results
            )

            # ── Step 10: Plain language translation ───────────────────────────
            try:
                plain_summary = await self.plain_formatter.format_full_portfolio(
                    full_recommendation=final,
                    amount=amount,
                    causal_chain=state["agent_outputs"].get("causal_chain"),
                )
                final["plain_language"] = plain_summary
            except Exception as e:
                final["plain_language"] = None

            state["final_recommendation"] = final

            # ── Step 11: Store in memory ───────────────────────────────────────
            await self.agents["memory_agent"].store_advice(user_id, {
                "query":           query,
                "recommendation":  final,
                "signals_used":    state["agent_outputs"].get("signal_watcher", {}).get("signals", []),
                "market_snapshot": state["agent_outputs"].get("signal_watcher", {}).get("market_snapshot", {}),
                "critic_verdict":  critic_result.get("verdict", "PASS"),
            })

            # ── Step 12: Snapshot driving signals for monitoring ───────────────
            try:
                from services.signal_monitor import create_signal_links_for_advice
                from models.models import AdviceRecord
                from sqlalchemy import select, desc

                # Get the just-created advice record
                advice_result = await self.db.execute(
                    select(AdviceRecord)
                    .where(AdviceRecord.user_id == user_id)
                    .order_by(desc(AdviceRecord.created_at))
                    .limit(1)
                )
                latest_advice = advice_result.scalar_one_or_none()

                if latest_advice:
                    driving_signals = state["agent_outputs"].get(
                        "signal_watcher", {}
                    ).get("signals", [])
                    await create_signal_links_for_advice(
                        self.db, latest_advice.id, driving_signals
                    )
                    await self.db.commit()
                    log.info("orchestrator.signal_links_created",
                             count=len(driving_signals))
            except Exception as e:
                await self.db.rollback()
                log.warning("orchestrator.signal_links_failed", error=str(e))

            elapsed = round(time.time() - start_time, 2)
            degraded = [
                name for name, out in state["agent_outputs"].items()
                if isinstance(out, dict) and "error" in out
            ]
            if degraded:
                log.warning("orchestrator.degraded", failed_agents=degraded)
            log.info("orchestrator.complete", elapsed_s=elapsed)

            return {
                "success":        True,
                "recommendation": final,
                "meta": {
                    "elapsed_seconds":    elapsed,
                    "agents_used":        list(state["agent_outputs"].keys()),
                    "degraded_components": degraded,
                    "conflicts_detected": len(conflicts),
                    "critic_verdict":     critic_result.get("verdict", "PASS"),
                }
            }

        except Exception as e:
            log.error("orchestrator.error", error=str(e))
            return {"success": False, "error": str(e)}

    async def _build_task_plan(self, state: dict) -> dict:
        profile_summary = self._summarize_profile(state["user_profile"])
        prompt = ORCHESTRATOR_PROMPT.format(
            query=state["query"],
            user_profile=profile_summary,
            amount=state["amount"],
            horizon=state["horizon"],
            country=state["country"],
        )
        try:
            plan = await call_llm_structured(
                prompt,
                _TaskPlanSchema,
                agent_name="orchestrator",
                max_retries=3,
            )
            return plan.model_dump()
        except Exception as e:
            logger.error("orchestrator.task_plan_failed", error=str(e)[:200])
            return {"task_plan": []}

    async def _execute_task_plan(self, state: dict, task_plan: dict):
        tasks     = task_plan["task_plan"]
        completed = set()

        while len(completed) < len(tasks):
            ready = [
                t for t in tasks
                if t["step"] not in completed
                and all(dep in completed for dep in t.get("depends_on", []))
            ]
            if not ready:
                break

            await asyncio.gather(*[
                asyncio.wait_for(self._run_single_task(state, task), timeout=90.0)
                for task in ready
            ], return_exceptions=True)
            for task in ready:
                completed.add(task["step"])

    async def _run_single_task(self, state: dict, task: dict):
        agent_name = task["agent"]
        agent      = self.agents.get(agent_name)
        if not agent:
            return

        start = time.time()
        log   = logger.bind(agent=agent_name)

        try:
            log.info("agent.start")

            agent_input = {
                "task_input":       task.get("input", ""),
                "user_profile":     state["user_profile"],
                "amount":           state["amount"],
                "horizon":          state["horizon"],
                "country":          state["country"],
                "query":            state["query"],
                "live_market_data": state["live_market_data"],
                **state["agent_outputs"],
            }

            if agent_name == "signal_watcher":
                result = await agent.get_current_signals()

            elif agent_name == "global_macro_agent":
                signals  = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                snapshot = state["agent_outputs"].get("signal_watcher", {}).get("market_snapshot", {})
                result   = await agent.analyze(signals, snapshot)

            elif agent_name == "research_agent":
                signals = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                result  = await agent.analyze(signals, state["country"])

            elif agent_name == "pattern_matcher":
                signals = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                result  = await agent.find_patterns(signals, state["country"])

            elif agent_name == "temporal_agent":
                signals = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                result  = await agent.assess_timelines(signals)

            elif agent_name == "portfolio_agent":
                result = await agent.run(agent_input)

            elif agent_name == "tax_agent":
                portfolio = state["agent_outputs"].get("portfolio_agent", {})
                result    = await agent.optimize(
                    portfolio, state["user_profile"], state["country"]
                )

            elif agent_name == "company_intelligence":
                research = state["agent_outputs"].get("research_agent", {})
                result   = await agent.analyze({
                    **agent_input,
                    "sectors_to_buy": (
                        research.get("sectors_analysis", {}).get("strong_buy", []) +
                        research.get("sectors_analysis", {}).get("buy", [])
                    ),
                    "sectors_to_avoid": (
                        research.get("sectors_analysis", {}).get("avoid", []) +
                        research.get("sectors_analysis", {}).get("strong_avoid", [])
                    ),
                })
                
            elif agent_name == "adversarial_agent":
                company_picks = state["agent_outputs"].get("company_intelligence", {})
                macro_context = state["agent_outputs"].get("global_macro_agent", {})
                all_companies = []
                for sector_pick in company_picks.get("sector_picks", []):
                    all_companies.extend(sector_pick.get("companies", []))
                
                surviving_picks = await agent.debate_picks(all_companies, macro_context)
                result = {"surviving_picks": surviving_picks}

            elif agent_name == "sentiment_aggregator":
                company_picks = state["agent_outputs"].get("company_intelligence", {})
                signals       = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
                snapshot      = state["agent_outputs"].get("signal_watcher", {}).get("market_snapshot", {})
                all_companies = []
                for sector_pick in company_picks.get("sector_picks", []):
                    all_companies.extend(sector_pick.get("companies", []))
                result = await agent.batch_score(all_companies, snapshot, signals)

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
            state["agent_outputs"][agent_name] = {"error": "timeout"}
        except Exception as e:
            log.error("agent.error", error=str(e))
            state["agent_outputs"][agent_name] = {"error": str(e)}

    async def _assemble_final_output(
        self,
        state: dict,
        critic_result: dict,
        technical_results: list,
    ) -> dict:
        portfolio     = state["agent_outputs"].get("portfolio_agent", {})
        tax           = state["agent_outputs"].get("tax_agent", {})
        temporal      = state["agent_outputs"].get("temporal_agent", {})
        research      = state["agent_outputs"].get("research_agent", {})
        patterns      = state["agent_outputs"].get("pattern_matcher", {})
        macro         = state["agent_outputs"].get("global_macro_agent", {})
        sentiment     = state["agent_outputs"].get("sentiment_aggregator", {})
        signals       = state["agent_outputs"].get("signal_watcher", {}).get("signals", [])
        intel         = state["agent_outputs"].get("market_intelligence", {})
        quant         = state["agent_outputs"].get("quant_risk", {})
        causal_chain  = state["agent_outputs"].get("causal_chain", {})

        return {
            "allocation":                  portfolio.get("allocation", {}),
            "sectors_to_buy":              portfolio.get("sectors_to_research", portfolio.get("sectors_to_buy", [])),
            "sectors_to_avoid":            portfolio.get("sectors_showing_risk", portfolio.get("sectors_to_avoid", [])),
            "rebalancing_triggers":        portfolio.get("rebalancing_triggers", []),
            "narrative":                   portfolio.get("narrative", ""),
            "confidence_score":            portfolio.get("analysis_confidence", portfolio.get("confidence_score", 0.5)),

            "tax_optimizations":           tax.get("optimizations", []),
            "post_tax_return_estimate":    tax.get("post_tax_return_estimate"),

            "reasoning_chain":             research.get("impact_chain", []),
            "causal_chain":                causal_chain,
            "root_cause_narrative":        research.get("root_cause_narrative", causal_chain.get("root_cause_narrative", "")),
            "event_timelines":             temporal.get("timelines", []),
            "historical_precedents":       patterns.get("best_analogues", []),
            "signals_used":                [s.get("title") for s in signals[:5]],
            
            "fii_dii_flows":               state["live_market_data"].get("fii_dii_flows", {}),
            "max_pain":                    intel.get("max_pain", {}),

            "company_picks":               state["agent_outputs"].get("company_intelligence", {}).get("sector_picks", []),
            "company_sentiments":          sentiment.get("sentiments", []),
            "sector_sentiment":            sentiment.get("sector_sentiment", {}),
            
            "bull_bear_debates":           state["agent_outputs"].get("adversarial_agent", {}).get("surviving_picks", []),
            "technical_analysis":          technical_results,
            
            "quant_risk_metrics":          quant,

            "bulk_deals":                  intel.get("bulk_deals", {}),
            "options_chain":               intel.get("options_chain", {}),

            "investment_strategy":         state["agent_outputs"].get("investment_manager", {}),
            "what_could_go_wrong":         critic_result.get("risks", []),
            "global_macro_summary":        macro.get("india_impact_summary"),
            "pre_market_brief":            macro.get("pre_market_brief"),
            "plain_language":              None,
            
            "disclaimer": (
                "This analysis is for educational and informational purposes only. "
                "It does not constitute investment advice under SEBI (Investment Advisers) "
                "Regulations, 2013. Please consult a SEBI-registered investment advisor "
                "before making any investment decisions."
            ),
        }

    def _summarize_profile(self, profile: dict) -> str:
        if not profile:
            return "New user, no history"
        return (
            f"Risk: {profile.get('risk_tolerance', 'moderate')}, "
            f"Experience: {profile.get('experience_level', 'intermediate')}"
        )