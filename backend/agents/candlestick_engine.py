"""
Candlestick Engine — Complete Technical Analysis for InvestAI

Modules:
1. CandleDataFetcher    — OHLCV data from Yahoo Finance (free, NSE stocks)
2. PatternDetector      — Detects 8 key candlestick patterns
3. VolatilityAnalyzer   — ATR, Bollinger Bands, HV, VIX regime
4. TradeManager         — Entry, stop loss, targets, position sizing, exit triggers
5. TechnicalAnalysisAgent — Master class combining all modules
"""

import json
import asyncio
import structlog
import httpx
import numpy as np
from datetime import datetime
from typing import Optional

from utils.llm_client import call_llm

logger = structlog.get_logger()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 1 — CANDLE DATA FETCHER
# ═════════════════════════════════════════════════════════════════════════════

class CandleDataFetcher:
    """
    Fetches real OHLCV candlestick data from Yahoo Finance.
    NSE stocks use .NS suffix (e.g. ONGC.NS, TCS.NS, HDFCBANK.NS)
    """

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    async def fetch(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "6mo"
    ) -> dict:
        """
        Fetch OHLCV candle data.
        interval: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo
        period:   1d, 5d, 1mo, 3mo, 6mo, 1y, 2y
        """
        # Add .NS suffix for NSE stocks if not present
        if "." not in symbol:
            yahoo_symbol = f"{symbol}.NS"
        else:
            yahoo_symbol = symbol

        url = f"{self.BASE_URL}/{yahoo_symbol}?interval={interval}&range={period}"

        try:
            async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
                r    = await client.get(url)
                data = r.json()

            result     = data["chart"]["result"][0]
            meta       = result["meta"]
            timestamps = result.get("timestamp", [])
            quotes     = result["indicators"]["quote"][0]

            candles = []
            for i in range(len(timestamps)):
                o = quotes["open"][i]
                h = quotes["high"][i]
                l = quotes["low"][i]
                c = quotes["close"][i]
                v = quotes.get("volume", [None] * len(timestamps))[i]

                # Skip candles with None values
                if None in (o, h, l, c):
                    continue

                candles.append({
                    "timestamp": timestamps[i],
                    "date":      datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d"),
                    "open":      round(o, 2),
                    "high":      round(h, 2),
                    "low":       round(l, 2),
                    "close":     round(c, 2),
                    "volume":    v or 0,
                    "body":      round(abs(c - o), 2),
                    "is_green":  c >= o,
                    "upper_wick": round(h - max(o, c), 2),
                    "lower_wick": round(min(o, c) - l, 2),
                })

            logger.info("candle_fetcher.success",
                        symbol=yahoo_symbol,
                        candles=len(candles),
                        interval=interval)

            return {
                "symbol":        symbol,
                "yahoo_symbol":  yahoo_symbol,
                "candles":       candles,
                "current_price": meta.get("regularMarketPrice"),
                "interval":      interval,
                "period":        period,
                "currency":      meta.get("currency", "INR"),
            }

        except Exception as e:
            logger.warning("candle_fetcher.error", symbol=symbol, error=str(e))
            return {"symbol": symbol, "candles": [], "error": str(e)}

    async def fetch_multi_timeframe(self, symbol: str) -> dict:
        """
        Fetch both daily and weekly candles simultaneously.
        Daily = entry timing precision
        Weekly = overall trend direction
        """
        daily_task  = self.fetch(symbol, interval="1d", period="6mo")
        weekly_task = self.fetch(symbol, interval="1wk", period="2y")

        daily, weekly = await asyncio.gather(daily_task, weekly_task)

        return {
            "symbol": symbol,
            "daily":  daily,
            "weekly": weekly,
        }


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 2 — PATTERN DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

class PatternDetector:
    """
    Detects 8 key candlestick patterns using pure Python math.
    No LLM needed for detection — fast and deterministic.
    LLM is only used to synthesize patterns into human readable text.
    """

    def detect_all(self, candles: list) -> dict:
        """Run all pattern detections on candle data."""
        if len(candles) < 3:
            return {"patterns": [], "overall_signal": "insufficient_data"}

        patterns_found = []

        # Single candle patterns (check last 3 candles)
        for i in range(max(0, len(candles) - 3), len(candles)):
            c = candles[i]

            doji = self._is_doji(c)
            if doji:
                patterns_found.append({**doji, "candle_index": i, "date": c["date"]})

            hammer = self._is_hammer(c)
            if hammer:
                patterns_found.append({**hammer, "candle_index": i, "date": c["date"]})

            shooting_star = self._is_shooting_star(c)
            if shooting_star:
                patterns_found.append({**shooting_star, "candle_index": i, "date": c["date"]})

            marubozu = self._is_marubozu(c)
            if marubozu:
                patterns_found.append({**marubozu, "candle_index": i, "date": c["date"]})

        # Two candle patterns (check last 2 candles)
        if len(candles) >= 2:
            last2 = candles[-2:]
            engulfing = self._is_engulfing(last2[0], last2[1])
            if engulfing:
                patterns_found.append({**engulfing, "date": last2[1]["date"]})

        # Three candle patterns (check last 3 candles)
        if len(candles) >= 3:
            last3 = candles[-3:]

            morning_star = self._is_morning_star(last3)
            if morning_star:
                patterns_found.append({**morning_star, "date": last3[2]["date"]})

            evening_star = self._is_evening_star(last3)
            if evening_star:
                patterns_found.append({**evening_star, "date": last3[2]["date"]})

            three_soldiers = self._is_three_soldiers(last3)
            if three_soldiers:
                patterns_found.append({**three_soldiers, "date": last3[2]["date"]})

            three_crows = self._is_three_crows(last3)
            if three_crows:
                patterns_found.append({**three_crows, "date": last3[2]["date"]})

        # Determine overall signal
        bullish = [p for p in patterns_found if p.get("signal") == "bullish"]
        bearish = [p for p in patterns_found if p.get("signal") == "bearish"]

        if len(bullish) > len(bearish):
            overall = "bullish"
        elif len(bearish) > len(bullish):
            overall = "bearish"
        elif len(bullish) == 0 and len(bearish) == 0:
            overall = "neutral"
        else:
            overall = "mixed"

        return {
            "patterns":           patterns_found,
            "bullish_count":      len(bullish),
            "bearish_count":      len(bearish),
            "overall_signal":     overall,
            "most_recent_candle": candles[-1] if candles else {},
        }

    # ── Single Candle Patterns ─────────────────────────────────────────────────

    def _is_doji(self, c: dict) -> Optional[dict]:
        """Doji: open ≈ close, indicating indecision."""
        if c["close"] == 0:
            return None
        body_pct = c["body"] / c["close"] * 100
        if body_pct < 0.3:  # Body less than 0.3% of price
            return {
                "pattern":     "Doji",
                "signal":      "neutral",
                "reliability": 0.55,
                "meaning":     "Market indecision — reversal likely, wait for confirmation",
                "action":      "Wait — direction unclear. Watch next candle for breakout direction.",
            }
        return None

    def _is_hammer(self, c: dict) -> Optional[dict]:
        """Hammer: small body at top, long lower wick. Bullish reversal."""
        if c["body"] == 0:
            return None
        lower_wick_ratio = c["lower_wick"] / c["body"] if c["body"] > 0 else 0
        upper_wick_ratio = c["upper_wick"] / c["body"] if c["body"] > 0 else 0

        if lower_wick_ratio >= 2 and upper_wick_ratio <= 0.5:
            return {
                "pattern":     "Hammer",
                "signal":      "bullish",
                "reliability": 0.72,
                "meaning":     "Buyers rejected lower prices strongly — bullish reversal signal",
                "action":      "Strong buy signal. Enter above hammer high. Stop below hammer low.",
            }
        return None

    def _is_shooting_star(self, c: dict) -> Optional[dict]:
        """Shooting Star: small body at bottom, long upper wick. Bearish reversal."""
        if c["body"] == 0:
            return None
        upper_wick_ratio = c["upper_wick"] / c["body"] if c["body"] > 0 else 0
        lower_wick_ratio = c["lower_wick"] / c["body"] if c["body"] > 0 else 0

        if upper_wick_ratio >= 2 and lower_wick_ratio <= 0.5 and not c["is_green"]:
            return {
                "pattern":     "Shooting Star",
                "signal":      "bearish",
                "reliability": 0.68,
                "meaning":     "Sellers rejected higher prices — bearish reversal signal",
                "action":      "Exit or reduce position. Sellers are taking control at this level.",
            }
        return None

    def _is_marubozu(self, c: dict) -> Optional[dict]:
        """Marubozu: full body, almost no wicks. Pure momentum."""
        if c["close"] == 0:
            return None
        total_range = c["high"] - c["low"]
        if total_range == 0:
            return None
        body_pct = c["body"] / total_range

        if body_pct >= 0.90:  # Body is 90%+ of range
            if c["is_green"]:
                return {
                    "pattern":     "Bullish Marubozu",
                    "signal":      "bullish",
                    "reliability": 0.75,
                    "meaning":     "Pure buying momentum — buyers dominated all session",
                    "action":      "Strong uptrend confirmation. Hold positions, add on dips.",
                }
            else:
                return {
                    "pattern":     "Bearish Marubozu",
                    "signal":      "bearish",
                    "reliability": 0.75,
                    "meaning":     "Pure selling momentum — sellers dominated all session",
                    "action":      "Strong downtrend. Exit positions, wait for reversal signal.",
                }
        return None

    # ── Two Candle Patterns ───────────────────────────────────────────────────

    def _is_engulfing(self, prev: dict, curr: dict) -> Optional[dict]:
        """Engulfing: current body completely contains previous body."""
        if curr["is_green"] and not prev["is_green"]:
            # Bullish engulfing: green swallows red
            if curr["open"] <= prev["close"] and curr["close"] >= prev["open"]:
                return {
                    "pattern":     "Bullish Engulfing",
                    "signal":      "bullish",
                    "reliability": 0.78,
                    "meaning":     "Strong buying — bulls completely overwhelmed bears",
                    "action":      "High conviction buy. Enter above engulfing candle high.",
                }
        elif not curr["is_green"] and prev["is_green"]:
            # Bearish engulfing: red swallows green
            if curr["open"] >= prev["close"] and curr["close"] <= prev["open"]:
                return {
                    "pattern":     "Bearish Engulfing",
                    "signal":      "bearish",
                    "reliability": 0.78,
                    "meaning":     "Strong selling — bears completely overwhelmed bulls",
                    "action":      "Exit positions immediately. Strong reversal signal.",
                }
        return None

    # ── Three Candle Patterns ─────────────────────────────────────────────────

    def _is_morning_star(self, candles: list) -> Optional[dict]:
        """Morning Star: red, small doji/body, green. Strong bullish reversal."""
        c1, c2, c3 = candles
        if (not c1["is_green"] and
            c2["body"] < c1["body"] * 0.3 and
            c3["is_green"] and
            c3["close"] > (c1["open"] + c1["close"]) / 2):
            return {
                "pattern":     "Morning Star",
                "signal":      "bullish",
                "reliability": 0.83,
                "meaning":     "Bottom confirmed — strong bullish reversal after downtrend",
                "action":      "Strong buy. This is a high-reliability bottom signal. Enter now.",
            }
        return None

    def _is_evening_star(self, candles: list) -> Optional[dict]:
        """Evening Star: green, small doji/body, red. Strong bearish reversal."""
        c1, c2, c3 = candles
        if (c1["is_green"] and
            c2["body"] < c1["body"] * 0.3 and
            not c3["is_green"] and
            c3["close"] < (c1["open"] + c1["close"]) / 2):
            return {
                "pattern":     "Evening Star",
                "signal":      "bearish",
                "reliability": 0.83,
                "meaning":     "Top confirmed — strong bearish reversal after uptrend",
                "action":      "EXIT immediately. One of the most reliable sell signals.",
            }
        return None

    def _is_three_soldiers(self, candles: list) -> Optional[dict]:
        """Three White Soldiers: three consecutive green candles. Strong uptrend."""
        c1, c2, c3 = candles
        if (c1["is_green"] and c2["is_green"] and c3["is_green"] and
            c2["close"] > c1["close"] and c3["close"] > c2["close"] and
            c2["open"] > c1["open"] and c3["open"] > c2["open"]):
            return {
                "pattern":     "Three White Soldiers",
                "signal":      "bullish",
                "reliability": 0.80,
                "meaning":     "Strong sustained buying — uptrend powerfully confirmed",
                "action":      "Hold all positions. Trend is strong. Trail stop loss upward.",
            }
        return None

    def _is_three_crows(self, candles: list) -> Optional[dict]:
        """Three Black Crows: three consecutive red candles. Strong downtrend."""
        c1, c2, c3 = candles
        if (not c1["is_green"] and not c2["is_green"] and not c3["is_green"] and
            c2["close"] < c1["close"] and c3["close"] < c2["close"] and
            c2["open"] < c1["open"] and c3["open"] < c2["open"]):
            return {
                "pattern":     "Three Black Crows",
                "signal":      "bearish",
                "reliability": 0.80,
                "meaning":     "Strong sustained selling — downtrend powerfully confirmed",
                "action":      "Exit all positions. Do not average down. Wait for reversal.",
            }
        return None


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 3 — VOLATILITY ANALYZER
# ═════════════════════════════════════════════════════════════════════════════

class VolatilityAnalyzer:
    """
    Calculates ATR, Bollinger Bands, Historical Volatility,
    and VIX-based regime classification.
    """

    def analyze(self, candles: list, india_vix: float = None) -> dict:
        """Full volatility analysis from candle data."""
        if len(candles) < 20:
            return {"error": "insufficient_data", "min_required": 20}

        closes  = [c["close"] for c in candles]
        highs   = [c["high"]  for c in candles]
        lows    = [c["low"]   for c in candles]

        atr           = self._calculate_atr(highs, lows, closes)
        bollinger     = self._calculate_bollinger(closes)
        hist_vol      = self._calculate_historical_volatility(closes)
        vix_regime    = self._classify_vix_regime(india_vix) if india_vix else {}
        support_resistance = self._find_support_resistance(candles)

        current_price = closes[-1]
        atr_pct       = round(atr / current_price * 100, 2)

        return {
            "current_price":       current_price,
            "atr":                 atr,
            "atr_percentage":      atr_pct,
            "bollinger":           bollinger,
            "historical_volatility": hist_vol,
            "vix_regime":          vix_regime,
            "support_resistance":  support_resistance,
            "volatility_summary":  self._summarize_volatility(atr_pct, hist_vol, vix_regime),
        }

    def _calculate_atr(self, highs: list, lows: list, closes: list, period: int = 14) -> float:
        """Average True Range — measures daily price movement range."""
        true_ranges = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i]  - closes[i-1])
            )
            true_ranges.append(tr)

        if not true_ranges:
            return 0

        atr = sum(true_ranges[-period:]) / min(period, len(true_ranges))
        return round(atr, 2)

    def _calculate_bollinger(self, closes: list, period: int = 20, std_dev: float = 2.0) -> dict:
        """Bollinger Bands — price relative to volatility range."""
        if len(closes) < period:
            return {}

        recent  = closes[-period:]
        middle  = np.mean(recent)
        std     = np.std(recent)
        upper   = middle + (std_dev * std)
        lower   = middle - (std_dev * std)
        current = closes[-1]
        width   = (upper - lower) / middle * 100

        # Position within bands (0 = at lower, 1 = at upper)
        band_position = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        squeeze = width < 5  # Bands are narrow — big move coming

        return {
            "upper":          round(upper, 2),
            "middle":         round(middle, 2),
            "lower":          round(lower, 2),
            "width_pct":      round(width, 2),
            "band_position":  round(band_position, 2),
            "squeeze":        squeeze,
            "interpretation": self._interpret_bollinger(current, upper, lower, middle, squeeze),
        }

    def _interpret_bollinger(self, price, upper, lower, middle, squeeze) -> str:
        if squeeze:
            return "SQUEEZE: Bands very narrow — major move imminent, direction unclear. Prepare for breakout."
        elif price >= upper * 0.99:
            return "OVERBOUGHT: Price at upper band — potential reversal zone. Consider taking profits."
        elif price <= lower * 1.01:
            return "OVERSOLD: Price at lower band — potential bounce zone. Watch for reversal candles."
        elif price > middle:
            return "BULLISH RANGE: Price above middle band — uptrend intact."
        else:
            return "BEARISH RANGE: Price below middle band — downtrend intact."

    def _calculate_historical_volatility(self, closes: list, period: int = 20) -> dict:
        """Historical volatility — how much the stock has been moving."""
        if len(closes) < period + 1:
            return {}

        log_returns = np.diff(np.log(closes[-period-1:]))
        daily_vol   = np.std(log_returns)
        annual_vol  = daily_vol * np.sqrt(252) * 100

        # Compare to 90-day average for context
        long_returns = np.diff(np.log(closes[-91:])) if len(closes) >= 92 else log_returns
        long_vol     = np.std(long_returns) * np.sqrt(252) * 100

        return {
            "daily_volatility":    round(daily_vol * 100, 2),
            "annual_volatility":   round(annual_vol, 2),
            "long_term_avg_vol":   round(long_vol, 2),
            "vol_regime":          "high" if annual_vol > long_vol * 1.3 else
                                   "low"  if annual_vol < long_vol * 0.7 else "normal",
            "interpretation":      f"Stock moving {annual_vol:.1f}% annually vs {long_vol:.1f}% long-term average",
        }

    def _classify_vix_regime(self, india_vix: float) -> dict:
        """Classify market regime from India VIX."""
        if india_vix < 13:
            return {
                "vix":        india_vix,
                "regime":     "ultra_low",
                "label":      "⚠️ EXTREME COMPLACENCY",
                "meaning":    "Market too calm — big move coming, protect positions",
                "position_size_multiplier": 0.7,
                "stop_loss_multiplier":     2.0,
                "action":     "Reduce position sizes. Use wider stops. Big move coming.",
            }
        elif india_vix < 17:
            return {
                "vix":        india_vix,
                "regime":     "normal",
                "label":      "✅ NORMAL CONDITIONS",
                "meaning":    "Healthy market — standard strategy applies",
                "position_size_multiplier": 1.0,
                "stop_loss_multiplier":     2.0,
                "action":     "Normal position sizing. Standard stops apply.",
            }
        elif india_vix < 22:
            return {
                "vix":        india_vix,
                "regime":     "elevated",
                "label":      "⚠️ ELEVATED FEAR",
                "meaning":    "Uncertainty rising — reduce exposure",
                "position_size_multiplier": 0.7,
                "stop_loss_multiplier":     2.5,
                "action":     "Reduce position size by 30%. Use wider stop losses.",
            }
        elif india_vix < 28:
            return {
                "vix":        india_vix,
                "regime":     "high_fear",
                "label":      "🔴 HIGH FEAR",
                "meaning":    "Fear-driven selling — best buying opportunities form here",
                "position_size_multiplier": 0.5,
                "stop_loss_multiplier":     3.0,
                "action":     "Buy quality stocks in tranches. Best long-term entry points.",
            }
        else:
            return {
                "vix":        india_vix,
                "regime":     "extreme_fear",
                "label":      "🚨 EXTREME PANIC",
                "meaning":    "Capitulation — market bottoms form in extreme fear",
                "position_size_multiplier": 0.3,
                "stop_loss_multiplier":     4.0,
                "action":     "Accumulate blue chips only. Buy in very small tranches.",
            }

    def _find_support_resistance(self, candles: list, lookback: int = 30) -> dict:
        """Find key support and resistance levels from recent candle highs/lows."""
        recent   = candles[-lookback:]
        highs    = sorted([c["high"]  for c in recent], reverse=True)
        lows     = sorted([c["low"]   for c in recent])
        current  = candles[-1]["close"]

        # Key levels
        resistance_levels = [h for h in highs[:5] if h > current]
        support_levels    = [l for l in lows[:5]  if l < current]

        return {
            "key_resistance": round(resistance_levels[0], 2) if resistance_levels else None,
            "key_support":    round(support_levels[0],    2) if support_levels    else None,
            "resistance_zone": round(resistance_levels[0] * 1.005, 2) if resistance_levels else None,
            "support_zone":    round(support_levels[0]    * 0.995, 2) if support_levels    else None,
        }

    def _summarize_volatility(self, atr_pct, hist_vol, vix_regime) -> str:
        regime = vix_regime.get("regime", "normal")
        annual = hist_vol.get("annual_volatility", 0)

        if regime in ("high_fear", "extreme_fear") and annual > 35:
            return "HIGH VOLATILITY ENVIRONMENT: Widen stops, reduce position sizes significantly"
        elif regime == "elevated" and annual > 25:
            return "ELEVATED VOLATILITY: Use wider stops than normal, reduce size by 30%"
        elif regime == "ultra_low":
            return "VOLATILITY COMPRESSION: Big move imminent — protect positions"
        else:
            return "NORMAL VOLATILITY: Standard position sizing and stops apply"


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 4 — TRADE MANAGER
# ═════════════════════════════════════════════════════════════════════════════

class TradeManager:
    """
    Produces complete trade management plan:
    - Entry price range
    - Stop loss (ATR-based, VIX-adjusted)
    - Target 1 and Target 2
    - Position sizing
    - Risk:Reward ratio
    - Exit triggers
    """

    def build_trade_plan(
        self,
        symbol: str,
        current_price: float,
        volatility_data: dict,
        pattern_data: dict,
        fundamental_signal: str,
        investment_amount: float = 100000,
        india_vix: float = 17,
    ) -> dict:
        """Build complete trade management plan."""

        atr            = volatility_data.get("atr", current_price * 0.02)
        bollinger      = volatility_data.get("bollinger", {})
        support_resist = volatility_data.get("support_resistance", {})
        vix_regime     = volatility_data.get("vix_regime", {})

        # VIX adjustment multipliers
        sl_multiplier   = vix_regime.get("stop_loss_multiplier", 2.0)
        size_multiplier = vix_regime.get("position_size_multiplier", 1.0)

        # ── Entry Range ───────────────────────────────────────────────────────
        entry_low  = round(current_price - (atr * 0.3), 2)
        entry_high = round(current_price + (atr * 0.2), 2)

        # Prefer entry near support if available
        support = support_resist.get("key_support")
        if support and support > entry_low:
            entry_low = round(support * 1.002, 2)  # 0.2% above support

        # ── Stop Loss ─────────────────────────────────────────────────────────
        stop_loss    = round(entry_low - (atr * sl_multiplier), 2)
        stop_loss_pct = round((entry_low - stop_loss) / entry_low * 100, 2)

        # Never let stop loss be more than 12% below entry
        if stop_loss_pct > 12:
            stop_loss     = round(entry_low * 0.88, 2)
            stop_loss_pct = 12.0

        # ── Targets ───────────────────────────────────────────────────────────
        risk          = entry_low - stop_loss
        target1       = round(entry_low + (risk * 2), 2)  # 1:2 risk:reward
        target2       = round(entry_low + (risk * 3.5), 2)  # 1:3.5 risk:reward

        # Use resistance as target if within range
        resistance = support_resist.get("key_resistance")
        if resistance and target1 < resistance < target2:
            target1 = round(resistance * 0.99, 2)  # Just below resistance

        # Bollinger upper as reference
        bb_upper = bollinger.get("upper")
        if bb_upper and target1 > bb_upper:
            target1 = round(bb_upper * 0.99, 2)

        # ── Risk:Reward ───────────────────────────────────────────────────────
        reward1        = target1 - entry_low
        reward2        = target2 - entry_low
        rr_ratio1      = round(reward1 / risk, 1) if risk > 0 else 0
        rr_ratio2      = round(reward2 / risk, 1) if risk > 0 else 0

        # ── Position Sizing ───────────────────────────────────────────────────
        # Risk 1.5% of portfolio per trade
        risk_per_trade = investment_amount * 0.015 * size_multiplier
        shares         = int(risk_per_trade / risk) if risk > 0 else 0
        position_value = round(shares * entry_low, 2)

        # Cap position at 20% of portfolio
        max_position    = investment_amount * 0.20
        if position_value > max_position:
            shares         = int(max_position / entry_low)
            position_value = round(shares * entry_low, 2)

        position_pct = round(position_value / investment_amount * 100, 1)

        # ── Entry Strategy ─────────────────────────────────────────────────────
        overall_signal = pattern_data.get("overall_signal", "neutral")
        if overall_signal == "bullish" and fundamental_signal in ("strong_buy", "buy"):
            entry_strategy = "IMMEDIATE ENTRY: Both technical and fundamental signals aligned. Buy 60% now, remaining 40% on any 3-5% dip."
        elif overall_signal == "bullish":
            entry_strategy = "BUY ON CONFIRMATION: Technical signal strong. Enter above today's high for momentum confirmation."
        elif overall_signal == "neutral":
            entry_strategy = "WAIT FOR CONFIRMATION: No clear pattern yet. Set buy alert at resistance breakout."
        else:
            entry_strategy = "AVOID: Technical signals bearish. Wait for reversal pattern before entering."

        # ── Exit Triggers ─────────────────────────────────────────────────────
        exit_triggers = [
            {
                "type":    "Target 1 (Book Partial Profit)",
                "trigger": f"Price reaches ₹{target1}",
                "action":  "Sell 50% of position, move stop loss to breakeven",
            },
            {
                "type":    "Target 2 (Full Profit)",
                "trigger": f"Price reaches ₹{target2}",
                "action":  "Sell remaining 50%. Full exit.",
            },
            {
                "type":    "Stop Loss (Capital Protection)",
                "trigger": f"Price closes below ₹{stop_loss}",
                "action":  "Exit FULL position immediately. No averaging down.",
            },
            {
                "type":    "Technical Exit (Bearish Pattern)",
                "trigger": "Evening Star or Bearish Engulfing forms above entry",
                "action":  "Exit 75% of position regardless of price level.",
            },
            {
                "type":    "Fundamental Exit (Thesis Broken)",
                "trigger": "Core signal that caused this recommendation reverses",
                "action":  "Exit full position within 48 hours. Thesis is invalid.",
            },
            {
                "type":    "Time Exit",
                "trigger": "If target not reached in 60 days",
                "action":  "Exit full position. Capital better deployed elsewhere.",
            },
        ]

        return {
            "symbol":             symbol,
            "current_price":      current_price,
            "entry": {
                "range_low":      entry_low,
                "range_high":     entry_high,
                "strategy":       entry_strategy,
                "best_entry":     entry_low,
            },
            "stop_loss": {
                "price":          stop_loss,
                "percentage":     stop_loss_pct,
                "basis":          f"Entry - ({sl_multiplier}× ATR of ₹{atr}), adjusted for VIX {india_vix}",
            },
            "targets": {
                "target1":        target1,
                "target1_return": round((target1 - entry_low) / entry_low * 100, 1),
                "target1_action": "Book 50% profit here",
                "target2":        target2,
                "target2_return": round((target2 - entry_low) / entry_low * 100, 1),
                "target2_action": "Exit remaining position",
            },
            "risk_reward": {
                "ratio_to_t1":    f"1:{rr_ratio1}",
                "ratio_to_t2":    f"1:{rr_ratio2}",
                "is_attractive":  rr_ratio1 >= 2.0,
            },
            "position_sizing": {
                "shares":         shares,
                "position_value": position_value,
                "portfolio_pct":  position_pct,
                "basis":          f"1.5% portfolio risk per trade, adjusted for VIX {india_vix}",
            },
            "exit_triggers":      exit_triggers,
            "hold_duration":      "45-70 days (typical signal lifecycle)",
        }


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 5 — MASTER TECHNICAL ANALYSIS AGENT
# ═════════════════════════════════════════════════════════════════════════════

TECHNICAL_SYNTHESIS_PROMPT = """You are a senior technical analyst specializing in Indian markets (NSE/BSE).

Synthesize this technical analysis into a clear, actionable recommendation for a retail investor.

SYMBOL: {symbol}
CURRENT PRICE: ₹{current_price}
WEEKLY TREND: {weekly_signal}
DAILY PATTERNS: {daily_patterns}
VOLATILITY: {volatility_summary}
TRADE PLAN: {trade_plan}
FUNDAMENTAL SIGNAL: {fundamental_signal}

Write a clear technical recommendation. Return ONLY valid JSON:
{{
  "technical_verdict": "strong_buy|buy|hold|sell|strong_sell",
  "conviction_score": 0-10,
  "one_line_summary": "Single clear sentence what to do",
  "weekly_trend": "The bigger picture trend direction",
  "entry_timing": "Specific guidance on when exactly to enter",
  "key_levels_to_watch": [
    "₹X is key support — if broken, exit immediately",
    "₹Y is key resistance — where sellers will emerge"
  ],
  "pattern_confluence": "How patterns align with fundamentals",
  "biggest_technical_risk": "What would invalidate this technical setup",
  "retail_friendly_explanation": "Explain the setup in simple language a beginner understands",
  "alert_prices": {{
    "buy_alert":  "Set buy alert at ₹X",
    "sell_alert": "Set profit alert at ₹X",
    "stop_alert": "Set stop loss alert at ₹X"
  }}
}}
"""


class TechnicalAnalysisAgent:
    """
    Master agent combining all technical analysis modules.
    Called by Company Intelligence after picking stocks.
    Adds entry/exit precision to fundamental recommendations.
    """

    def __init__(self):
        self.fetcher   = CandleDataFetcher()
        self.detector  = PatternDetector()
        self.vol       = VolatilityAnalyzer()
        self.trade_mgr = TradeManager()

    async def analyze(
        self,
        symbol: str,
        fundamental_signal: str = "buy",
        investment_amount: float = 100000,
        india_vix: float = 17.0,
    ) -> dict:
        """
        Complete technical analysis for a stock.
        Returns full trade plan with entry, stop, targets, exit triggers.
        """
        log = logger.bind(symbol=symbol)
        log.info("technical_agent.start")

        # Step 1: Fetch multi-timeframe candle data
        candle_data = await self.fetcher.fetch_multi_timeframe(symbol)

        daily_candles  = candle_data.get("daily",  {}).get("candles", [])
        weekly_candles = candle_data.get("weekly", {}).get("candles", [])
        current_price  = candle_data.get("daily",  {}).get("current_price", 0)

        if not daily_candles or not current_price:
            log.warning("technical_agent.no_data")
            return {
                "symbol":  symbol,
                "error":   "no_candle_data",
                "message": f"Could not fetch candle data for {symbol}. Check NSE symbol.",
            }

        # Step 2: Detect patterns on both timeframes
        daily_patterns  = self.detector.detect_all(daily_candles)
        weekly_patterns = self.detector.detect_all(weekly_candles) if weekly_candles else {}

        # Step 3: Volatility analysis (use daily candles)
        vol_data = self.vol.analyze(daily_candles, india_vix=india_vix)

        # Step 4: Build complete trade plan
        trade_plan = self.trade_mgr.build_trade_plan(
            symbol=symbol,
            current_price=current_price,
            volatility_data=vol_data,
            pattern_data=daily_patterns,
            fundamental_signal=fundamental_signal,
            investment_amount=investment_amount,
            india_vix=india_vix,
        )

        # Step 5: LLM synthesis into human-readable recommendation
        synthesis = await self._synthesize(
            symbol=symbol,
            current_price=current_price,
            daily_patterns=daily_patterns,
            weekly_signal=weekly_patterns.get("overall_signal", "unknown"),
            vol_data=vol_data,
            trade_plan=trade_plan,
            fundamental_signal=fundamental_signal,
        )

        log.info("technical_agent.complete",
                 symbol=symbol,
                 verdict=synthesis.get("technical_verdict"),
                 conviction=synthesis.get("conviction_score"))

        return {
            "symbol":            symbol,
            "current_price":     current_price,
            "daily_patterns":    daily_patterns,
            "weekly_patterns":   weekly_patterns,
            "volatility":        vol_data,
            "trade_plan":        trade_plan,
            "synthesis":         synthesis,
            "analyzed_at":       datetime.utcnow().isoformat(),
        }

    async def analyze_batch(
        self,
        stocks: list,
        investment_amount: float = 100000,
        india_vix: float = 17.0,
    ) -> list:
        """
        Analyze multiple stocks concurrently.
        Called by Company Intelligence after picking sector stocks.
        """
        tasks = [
            self.analyze(
                symbol=s.get("nse_symbol", s.get("symbol", s)) if isinstance(s, dict) else s,
                fundamental_signal=s.get("signal_alignment", "buy") if isinstance(s, dict) else "buy",
                investment_amount=investment_amount,
                india_vix=india_vix,
            )
            for s in stocks[:6]  # Limit to 6 concurrent calls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid   = [r for r in results if isinstance(r, dict) and "error" not in r]

        # Sort by conviction score
        return sorted(
            valid,
            key=lambda x: x.get("synthesis", {}).get("conviction_score", 0),
            reverse=True
        )

    async def _synthesize(
        self,
        symbol: str,
        current_price: float,
        daily_patterns: dict,
        weekly_signal: str,
        vol_data: dict,
        trade_plan: dict,
        fundamental_signal: str,
    ) -> dict:
        """Use LLM to synthesize all technical signals into human-readable output."""
        prompt = TECHNICAL_SYNTHESIS_PROMPT.format(
            symbol=symbol,
            current_price=current_price,
            weekly_signal=weekly_signal,
            daily_patterns=json.dumps({
                "patterns":       daily_patterns.get("patterns", []),
                "overall_signal": daily_patterns.get("overall_signal"),
                "bullish_count":  daily_patterns.get("bullish_count"),
                "bearish_count":  daily_patterns.get("bearish_count"),
            }, indent=2),
            volatility_summary=json.dumps({
                "atr":            vol_data.get("atr"),
                "atr_pct":        vol_data.get("atr_percentage"),
                "bollinger":      vol_data.get("bollinger", {}).get("interpretation"),
                "hist_vol":       vol_data.get("historical_volatility", {}).get("annual_volatility"),
                "vix_regime":     vol_data.get("vix_regime", {}).get("label"),
                "summary":        vol_data.get("volatility_summary"),
            }, indent=2),
            trade_plan=json.dumps({
                "entry":         trade_plan.get("entry"),
                "stop_loss":     trade_plan.get("stop_loss"),
                "targets":       trade_plan.get("targets"),
                "risk_reward":   trade_plan.get("risk_reward"),
                "position_size": trade_plan.get("position_sizing"),
            }, indent=2),
            fundamental_signal=fundamental_signal,
        )

        try:
            text   = await call_llm(prompt, agent_name="technical_analysis_agent")
            return json.loads(text)
        except Exception as e:
            logger.warning("technical_agent.synthesis_error", error=str(e))
            # Return basic synthesis if LLM fails
            overall = daily_patterns.get("overall_signal", "neutral")
            return {
                "technical_verdict":   "buy" if overall == "bullish" else
                                       "sell" if overall == "bearish" else "hold",
                "conviction_score":    6 if overall in ("bullish", "bearish") else 4,
                "one_line_summary":    f"{symbol} showing {overall} technical pattern at ₹{current_price}",
                "entry_timing":        trade_plan.get("entry", {}).get("strategy", ""),
                "key_levels_to_watch": [
                    f"Support: ₹{vol_data.get('support_resistance', {}).get('key_support', 'N/A')}",
                    f"Resistance: ₹{vol_data.get('support_resistance', {}).get('key_resistance', 'N/A')}",
                ],
                "alert_prices": {
                    "buy_alert":  f"₹{trade_plan.get('entry', {}).get('range_low', current_price)}",
                    "sell_alert": f"₹{trade_plan.get('targets', {}).get('target1', current_price * 1.1)}",
                    "stop_alert": f"₹{trade_plan.get('stop_loss', {}).get('price', current_price * 0.92)}",
                },
            }