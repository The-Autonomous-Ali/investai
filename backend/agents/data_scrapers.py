"""
Live Data Scrapers — Fetching Alternative Alpha (FII/DII Flows & Max Pain).
"""
import httpx
import structlog
from datetime import datetime

logger = structlog.get_logger()

class NSEDataScraper:
    def __init__(self):
        # NSE requires standard browser headers to not block requests
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        }
        self.base_url = "https://www.nseindia.com"
        self.session = httpx.AsyncClient(headers=self.headers, timeout=15.0)

    async def _get_cookies(self):
        """NSE APIs require a valid session cookie first."""
        try:
            await self.session.get(self.base_url)
        except Exception as e:
            logger.warning("failed_to_fetch_nse_cookies", error=str(e))

    async def fetch_fii_dii_flows(self) -> dict:
        """Fetches today's FII and DII cash market activity."""
        log = logger.bind(action="fetch_fii_dii")
        log.info("start")
        await self._get_cookies()
        
        # NSE FII/DII API endpoint
        url = f"{self.base_url}/api/fiidiiTradeReact"
        try:
            response = await self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                # Parse the standard NSE JSON structure
                fii_data = next((item for item in data if item.get('category') == 'FII/FPI *'), None)
                dii_data = next((item for item in data if item.get('category') == 'DII **'), None)
                
                fii_net = float(fii_data['net']) if fii_data else 0.0
                dii_net = float(dii_data['net']) if dii_data else 0.0
                
                return {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "fii_net_crores": fii_net,
                    "dii_net_crores": dii_net,
                    "net_institutional_flow": fii_net + dii_net,
                    "market_sentiment": "Bullish" if (fii_net + dii_net) > 0 else "Bearish"
                }
            else:
                log.warning("bad_status", status=response.status_code)
                return {"error": "Failed to fetch FII/DII data"}
        except Exception as e:
            log.error("exception", error=str(e))
            return {"error": str(e)}

    async def calculate_max_pain(self, symbol: str) -> dict:
        """Fetches Options Chain and calculates Max Pain strike price."""
        log = logger.bind(action="max_pain", symbol=symbol)
        log.info("start")
        await self._get_cookies()
        
        url = f"{self.base_url}/api/option-chain-equities?symbol={symbol}"
        if symbol in ["NIFTY", "BANKNIFTY"]:
            url = f"{self.base_url}/api/option-chain-indices?symbol={symbol}"

        try:
            response = await self.session.get(url)
            if response.status_code != 200:
                return {"error": f"Failed to fetch option chain for {symbol}"}
            
            data = response.json()
            records = data.get("records", {})
            expiry_dates = records.get("expiryDates", [])
            
            if not expiry_dates:
                return {"error": "No expiry dates found"}
                
            current_expiry = expiry_dates[0]
            options = [opt for opt in records.get("data", []) if opt.get("expiryDate") == current_expiry]
            
            # Max Pain Math: Strike with minimum intrinsic value loss for Option Sellers
            strikes = [opt["strikePrice"] for opt in options]
            pain_values = {}
            
            for potential_expiry_strike in strikes:
                total_pain = 0.0
                for opt in options:
                    strike = opt["strikePrice"]
                    ce_oi = opt.get("CE", {}).get("openInterest", 0)
                    pe_oi = opt.get("PE", {}).get("openInterest", 0)
                    
                    if potential_expiry_strike > strike:
                        total_pain += (potential_expiry_strike - strike) * ce_oi
                    if potential_expiry_strike < strike:
                        total_pain += (strike - potential_expiry_strike) * pe_oi
                        
                pain_values[potential_expiry_strike] = total_pain

            max_pain_strike = min(pain_values, key=pain_values.get)
            
            return {
                "symbol": symbol,
                "expiry": current_expiry,
                "max_pain_strike": max_pain_strike,
                "insight": f"Market makers will heavily defend the {max_pain_strike} level."
            }
        except Exception as e:
            log.error("exception", error=str(e))
            return {"error": str(e)}