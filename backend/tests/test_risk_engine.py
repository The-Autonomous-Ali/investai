"""Tests for RiskEngine — yfinance mocked with synthetic data."""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from agents.risk_engine import RiskEngine


@pytest.fixture
def engine():
    return RiskEngine()


@pytest.fixture
def mock_price_data():
    """Generate synthetic price data for 2 stocks over 252 trading days."""
    dates = pd.bdate_range(end=datetime.now(), periods=252)
    np.random.seed(42)
    reliance = 2500 + np.cumsum(np.random.normal(0.5, 15, 252))
    tcs = 3500 + np.cumsum(np.random.normal(0.3, 12, 252))
    df = pd.DataFrame({"RELIANCE.NS": reliance, "TCS.NS": tcs}, index=dates)
    return df


@pytest.mark.asyncio
async def test_calculate_portfolio_risk(engine, mock_price_data):
    picks = [
        {"nse_symbol": "RELIANCE", "final_weight": 60},
        {"nse_symbol": "TCS", "final_weight": 40},
    ]

    # Build multi-index DataFrame matching yfinance output format
    close_data = mock_price_data.copy()
    multi_col = pd.MultiIndex.from_tuples([("Close", c) for c in close_data.columns])
    close_data.columns = multi_col

    with patch("agents.risk_engine.yf.download") as mock_yf:
        mock_yf.return_value = close_data
        result = await engine.calculate_portfolio_risk(picks, 1000000)

    assert "portfolio_expected_return_annual" in result
    assert "daily_value_at_risk_inr" in result
    assert "monte_carlo_1yr_projection" in result
    assert result["var_confidence_level"] == "95%"
    assert isinstance(result["daily_value_at_risk_inr"], float)


@pytest.mark.asyncio
async def test_empty_picks(engine):
    result = await engine.calculate_portfolio_risk([], 100000)
    assert "error" in result


@pytest.mark.asyncio
async def test_risk_engine_handles_download_failure(engine):
    picks = [{"nse_symbol": "BAD", "final_weight": 100}]
    with patch("agents.risk_engine.yf.download") as mock_yf:
        mock_yf.side_effect = Exception("Network error")
        result = await engine.calculate_portfolio_risk(picks, 100000)

    assert "error" in result
