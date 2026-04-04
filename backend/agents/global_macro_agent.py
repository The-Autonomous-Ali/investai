"""
Global Macro Agent — Layer 1 of the data intelligence architecture.

Sits ABOVE Signal Watcher. Monitors global macro indicators and scores
their India-specific impact BEFORE passing to the rest of the pipeline.

Tracks:
- Central bank policy divergence (Fed vs RBI vs ECB)
- US 10Y yield movements (FII flow predictor)
- Dollar Index (DXY) — rupee impact
- Global risk-on/risk-off sentiment
- Commodity super-cycle indicators
- Geopolitical risk scoring
"""
import json
import structlog
from datetime import datetime

from utils.llm_client import call_llm

logger = structlog.get_logger()

GLOBAL_MACRO_PROMPT = """You are a global macro analyst specializing in how international events create ripple effects in Indian markets.

CURRENT GLOBAL SIGNALS: {signals}
CURRENT MARKET SNAPSHOT: {snapshot}

Your job is to:
1. Score each signal's India impact (0-10)
2. Identify the PRIMARY transmission mechanism (how does it reach India?)
3. Map affected Indian sectors
4. Identify the KEY VARIABLE to watch (what confirms or denies the impact?)
5. Give an overall global risk score for India right now

Return ONLY valid JSON:
{{
  "global_risk_score": 0-10,
  "risk_regime": "risk_on|risk_off|neutral",
  "primary_global_theme": "e.g. Fed hawkishness + strong dollar + commodity spike",
  "india_impact_summary": "2-3 sentence summary of how global environment affects India right now",
  "signal_scores": [
    {{
      "signal_title": "Fed signals rates higher",
      "india_impact_score": 8.5,
      "transmission_mechanism": "Fed hawkish -> DXY strengthens -> FII sell India -> Nifty falls + INR weakens",
      "affected_india_sectors": {{
        "it": "positive (INR depreciation boosts IT exports)",
        "banking": "negative (FII selling pressure)",
        "real_estate": "negative (rate premium rises)",
        "gold": "positive (safe haven)"
      }},
      "key_variable_to_watch": "US 10Y yield crossing 4.5% triggers accelerated FII outflows",
      "time_horizon": "1-3 months"
    }}
  ],
  "macro_tailwinds_for_india": [
    "China slowdown -> India gains as manufacturing alternative",
    "Oil below $85 -> CAD improves -> INR strengthens"
  ],
  "macro_headwinds_for_india": [
    "Strong dollar -> FII outflows -> Nifty correction",
    "High US yields -> EM outflows"
  ],
  "watch_list": [
    {{
      "indicator": "US 10Y Treasury Yield",
      "current": "4.42%",
      "danger_level": "above 4.6%",
      "safe_level": "below 4.2%",
      "india_action": "If crosses 4.6%: reduce equity exposure, increase gold"
    }}
  ],
  "pre_market_brief": "One paragraph briefing for Indian investors before NSE opens at 9:15 AM"
}}
"""

TIMEZONE_ALERT_PROMPT = """You are monitoring global markets overnight (when Indian markets are closed).

A significant event just occurred:
EVENT: {event_title}
DETAILS: {event_details}
TIME: {event_time} UTC
CURRENT US 10Y YIELD: {us_10y}
CURRENT DXY: {dxy}
CURRENT BRENT: {brent}

Indian market opens at 9:15 AM IST ({ist_open} UTC).
Time until India open: {hours_until_open} hours.

Assess:
1. Will this move Indian markets at open?
2. Which sectors will be hit first?
3. What should investors do before open?

Return ONLY valid JSON:
{{
  "expected_nifty_move": "+/-X% at open",
  "confidence": 0.0-1.0,
  "sectors_to_watch_at_open": [
    {{"sector": "Aviation", "expected_move": "-2 to -3%", "reason": "Oil spike overnight"}}
  ],
  "pre_open_action": "Buy/Sell/Hold recommendation before 9:15 AM",
  "alert_urgency": "high|medium|low",
  "alert_message": "Short WhatsApp-style alert for user"
}}
"""


class GlobalMacroAgent:
    """
    Processes global signals and scores India impact.
    Runs BEFORE the main agent pipeline to enrich signal context.
    Also handles timezone arbitrage — overnight global events.
    """

    def __init__(self, db_session=None, redis_client=None):
        self.db    = db_session
        self.redis = redis_client

    async def analyze(self, signals: list, market_snapshot: dict) -> dict:
        """
        Score all global signals for India impact.
        Called by Orchestrator before Research Agent runs.
        """
        if not signals:
            return {"global_risk_score": 5, "risk_regime": "neutral", "signal_scores": []}

        log = logger.bind(signal_count=len(signals))
        log.info("global_macro_agent.start")

        # Filter to global signals only (non-India sources)
        global_signals = [
            s for s in signals
            if s.get("geography", "global") != "india"
        ]

        # Include all signals if no global ones found
        if not global_signals:
            global_signals = signals[:5]

        prompt = GLOBAL_MACRO_PROMPT.format(
            signals=json.dumps([
                {k: v for k, v in s.items() if k in [
                    "title", "signal_type", "urgency", "importance_score",
                    "entities_mentioned", "geography", "chain_effects"
                ]}
                for s in global_signals[:8]
            ], indent=2),
            snapshot=json.dumps({
                k: v for k, v in market_snapshot.items()
                if k in ["us_10y_yield", "dxy", "vix_us", "brent_crude",
                         "sp500", "china_csi300", "usd_inr", "fii_today"]
            }, indent=2),
        )

        text = await call_llm(prompt, agent_name="global_macro_agent")
        result = json.loads(text)

        log.info("global_macro_agent.complete",
                 risk_score=result.get("global_risk_score"),
                 regime=result.get("risk_regime"))
        return result

    async def check_timezone_arbitrage(self, event: dict, market_snapshot: dict) -> dict:
        """
        OpenClaw-style timezone intelligence.
        When a major global event happens while India sleeps,
        calculate the expected India market open impact.
        """
        now_utc = datetime.utcnow()
        # NSE opens at 9:15 AM IST = 3:45 AM UTC
        nse_open_utc = now_utc.replace(hour=3, minute=45, second=0)
        if now_utc.hour >= 4:
            # Past today's open — calculate for tomorrow
            from datetime import timedelta
            nse_open_utc += timedelta(days=1)

        hours_until_open = max(0, (nse_open_utc - now_utc).seconds / 3600)

        prompt = TIMEZONE_ALERT_PROMPT.format(
            event_title=event.get("title", ""),
            event_details=event.get("chain_effects", []),
            event_time=now_utc.strftime("%H:%M"),
            ist_open="03:45",
            hours_until_open=round(hours_until_open, 1),
            us_10y=market_snapshot.get("us_10y_yield", {}).get("value", "N/A"),
            dxy=market_snapshot.get("dxy", {}).get("value", "N/A"),
            brent=market_snapshot.get("brent_crude", {}).get("value", "N/A"),
        )

        text = await call_llm(prompt, agent_name="global_macro_agent")
        result = json.loads(text)

        logger.info("global_macro_agent.timezone_alert",
                    urgency=result.get("alert_urgency"),
                    nifty_move=result.get("expected_nifty_move"))
        return result

    async def get_pre_market_brief(self, signals: list, snapshot: dict) -> str:
        """
        Generate a pre-market brief for users before NSE opens.
        Called at 8:30 AM IST by the background worker.
        """
        result = await self.analyze(signals, snapshot)
        return result.get("pre_market_brief", "No brief available.")