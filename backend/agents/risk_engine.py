"""
Risk Engine — Quantitative Analysis, Value at Risk (VaR), and Monte Carlo Simulations.
"""
import asyncio
import numpy as np
import pandas as pd
import yfinance as yf
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()

class RiskEngine:
    def __init__(self):
        self.confidence_level = 0.95  # 95% confidence interval
        self.trading_days = 252       # Trading days in a year

    async def calculate_portfolio_risk(self, surviving_picks: list, total_amount: float) -> dict:
        log = logger.bind(picks=len(surviving_picks))
        log.info("risk_engine.start")

        if not surviving_picks:
            return {"error": "No stocks provided for risk analysis."}

        # 1. Extract symbols and format them for Yahoo Finance India (NSE)
        symbols = []
        weights = []
        
        for pick in surviving_picks:
            sym = pick.get("nse_symbol")
            if sym:
                symbols.append(f"{sym}.NS") # .NS is the Yahoo Finance suffix for NSE
                weights.append(pick.get("final_weight", 100 / len(surviving_picks))) 

        weights = np.array(weights) / sum(weights)

        try:
            # 2. Fetch 1 year of historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            
            log.info("risk_engine.fetching_data", symbols=symbols)
            data = await asyncio.to_thread(
                yf.download, symbols, start=start_date, end=end_date, progress=False
            )
            
            if len(symbols) == 1:
                closes = pd.DataFrame(data['Close'])
                closes.columns = symbols
            else:
                closes = data['Close']

            # 3. Calculate Daily Returns & Covariance
            daily_returns = closes.pct_change().dropna()
            cov_matrix = daily_returns.cov() * self.trading_days
            mean_returns = daily_returns.mean() * self.trading_days

            # 4. Portfolio Variance and Volatility
            portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
            portfolio_volatility = np.sqrt(portfolio_variance)
            portfolio_expected_return = np.sum(mean_returns * weights)

            # 5. Calculate Value at Risk (VaR)
            daily_volatility = portfolio_volatility / np.sqrt(self.trading_days)
            z_score = 1.645 
            daily_var_percentage = z_score * daily_volatility
            daily_var_inr = total_amount * daily_var_percentage

            # 6. Basic Monte Carlo Simulation
            mc_simulations = 1000
            mc_results = []
            for _ in range(mc_simulations):
                simulated_return = np.random.normal(portfolio_expected_return, portfolio_volatility)
                simulated_value = total_amount * (1 + simulated_return)
                mc_results.append(simulated_value)
            
            mc_results = np.array(mc_results)
            best_case = np.percentile(mc_results, 95)
            worst_case = np.percentile(mc_results, 5)

            log.info("risk_engine.complete", daily_var=daily_var_inr)

            # FIX: Added float() wrappers to make the numbers JSON compliant
            return {
                "portfolio_expected_return_annual": float(round(portfolio_expected_return * 100, 2)),
                "portfolio_volatility_annual": float(round(portfolio_volatility * 100, 2)),
                "daily_value_at_risk_inr": float(round(daily_var_inr, 2)),
                "var_confidence_level": "95%",
                "monte_carlo_1yr_projection": {
                    "expected_value": float(round(np.mean(mc_results), 2)),
                    "best_case_95": float(round(best_case, 2)),
                    "worst_case_05": float(round(worst_case, 2))
                },
                "risk_narrative": (
                    f"Based on historical data, there is a 95% probability that your ₹{total_amount:,.0f} portfolio "
                    f"will not lose more than ₹{float(daily_var_inr):,.0f} in a single trading day."
                )
            }

        except Exception as e:
            log.error("risk_engine.failed", error=str(e))
            return {"error": f"Risk calculation failed: {str(e)}"}