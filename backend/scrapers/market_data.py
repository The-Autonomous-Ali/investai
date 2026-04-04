"""
Market Data Scraper — pulls live Indian market data using yfinance (free).

Provides:
- Live index prices (Nifty 50, Sensex, Bank Nifty, India VIX)
- Sector index performance
- Individual stock data
- Currency and commodity data relevant to India

All data is fetched via yfinance which uses Yahoo Finance — no API key needed.
"""
import yfinance as yf
import structlog
from datetime import datetime, timezone
from typing import Optional

logger = structlog.get_logger()

# Key Indian market tickers on Yahoo Finance
INDIA_INDICES = {
    "NIFTY_50": "^NSEI",
    "SENSEX": "^BSESN",
    "BANK_NIFTY": "^NSEBANK",
    "INDIA_VIX": "^INDIAVIX",
    "NIFTY_IT": "^CNXIT",
    "NIFTY_PHARMA": "^CNXPHARMA",
    "NIFTY_ENERGY": "^CNXENERGY",
    "NIFTY_FMCG": "^CNXFMCG",
    "NIFTY_METAL": "^CNXMETAL",
    "NIFTY_REALTY": "^CNXREALTY",
    "NIFTY_AUTO": "^CNXAUTO",
    "NIFTY_INFRA": "^CNXINFRA",
}

GLOBAL_CONTEXT = {
    "BRENT_CRUDE": "BZ=F",
    "GOLD": "GC=F",
    "USD_INR": "INR=X",
    "DXY": "DX-Y.NYB",
    "US_10Y": "^TNX",
}

# Top Indian stocks by market cap
TOP_STOCKS = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "INFY": "INFY.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "ONGC": "ONGC.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "ITC": "ITC.NS",
    "SBIN": "SBIN.NS",
    "ASIANPAINT": "ASIANPAINT.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "WIPRO": "WIPRO.NS",
    "HCLTECH": "HCLTECH.NS",
    "COALINDIA": "COALINDIA.NS",
    "ADANIGREEN": "ADANIGREEN.NS",
    "HAL": "HAL.NS",
    "TATAPOWER": "TATAPOWER.NS",
    "OIL": "OIL.NS",
}


async def get_market_snapshot() -> dict:
    """
    Get a complete snapshot of Indian markets + global context.
    Used by the orchestrator to provide market context to all agents.
    """
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "indices": {},
        "global": {},
        "top_movers": {"gainers": [], "losers": []},
    }

    # Fetch indices
    for name, ticker in INDIA_INDICES.items():
        data = _get_ticker_data(ticker)
        if data:
            snapshot["indices"][name] = data

    # Fetch global context
    for name, ticker in GLOBAL_CONTEXT.items():
        data = _get_ticker_data(ticker)
        if data:
            snapshot["global"][name] = data

    # Fetch top stocks for movers
    movers = []
    for name, ticker in TOP_STOCKS.items():
        data = _get_ticker_data(ticker)
        if data:
            data["symbol"] = name
            movers.append(data)

    # Sort by change percentage
    movers.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    snapshot["top_movers"]["gainers"] = movers[:5]
    snapshot["top_movers"]["losers"] = movers[-5:]

    logger.info("market_data.snapshot.complete", indices=len(snapshot["indices"]))
    return snapshot


async def get_stock_data(symbol: str) -> Optional[dict]:
    """
    Get detailed data for a single stock.
    Symbol should be NSE symbol (e.g., 'ONGC', 'TCS').
    """
    ticker_symbol = f"{symbol.upper()}.NS"
    return _get_ticker_data(ticker_symbol, detailed=True)


async def get_sector_performance() -> dict:
    """Get performance of all sector indices — used for sector rotation analysis."""
    sectors = {}
    sector_indices = {k: v for k, v in INDIA_INDICES.items() if k.startswith("NIFTY_") and k != "NIFTY_50"}

    for name, ticker in sector_indices.items():
        data = _get_ticker_data(ticker)
        if data:
            sectors[name.replace("NIFTY_", "")] = data

    return sectors


def _get_ticker_data(ticker_symbol: str, detailed: bool = False) -> Optional[dict]:
    """Fetch data for a single ticker using yfinance."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.fast_info

        data = {
            "price": round(info.last_price, 2) if hasattr(info, 'last_price') and info.last_price else None,
            "previous_close": round(info.previous_close, 2) if hasattr(info, 'previous_close') and info.previous_close else None,
        }

        # Calculate change
        if data["price"] and data["previous_close"] and data["previous_close"] > 0:
            change = data["price"] - data["previous_close"]
            data["change"] = round(change, 2)
            data["change_pct"] = round((change / data["previous_close"]) * 100, 2)
        else:
            data["change"] = 0
            data["change_pct"] = 0

        if detailed:
            full_info = ticker.info
            data.update({
                "name": full_info.get("longName", ""),
                "sector": full_info.get("sector", ""),
                "market_cap": full_info.get("marketCap"),
                "pe_ratio": full_info.get("trailingPE"),
                "pb_ratio": full_info.get("priceToBook"),
                "dividend_yield": full_info.get("dividendYield"),
                "fifty_two_week_high": full_info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": full_info.get("fiftyTwoWeekLow"),
                "avg_volume": full_info.get("averageVolume"),
            })

        return data

    except Exception as e:
        logger.warning("market_data.ticker.error", ticker=ticker_symbol, error=str(e))
        return None
