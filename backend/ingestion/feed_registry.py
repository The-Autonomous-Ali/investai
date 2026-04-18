"""Feed registry — the single source of truth for every data source.

Every connector instance the banker pulls from is declared here. The
ingestion dispatcher imports `get_all_connectors()` and iterates the
list, calling `.run()` on each on its own schedule.

Tier convention:
    1 = official/government (central banks, regulators, FRED)
    2 = major financial media (ET, Mint, Moneycontrol, Reuters)
    3 = secondary (aggregators, curated sources)

Region convention (source-based, not impact-based):
    us | eu | uk | jp | cn | in | global

Category convention:
    monetary | regulatory | markets | corporate | economy |
    commodities | capital_flow | macro | price | general

Adding a new feed: import the connector class, append an instance to
the relevant list. No other code needs to change.

China (C4) and scrape-based feeds (NSDL FPI, PBOC) are NOT in here yet
— they need concrete ScrapeConnector subclasses first. This registry
will grow as those land.
"""
from __future__ import annotations

from ingestion.base import BaseConnector
from ingestion.connectors.fred import FredSeriesConnector
from ingestion.connectors.rss import RSSConnector
from ingestion.connectors.yfinance_prices import YFinancePricesConnector


# ---------------------------------------------------------------------------
# RSS feeds — grouped by source region
# ---------------------------------------------------------------------------

INDIA_RSS = [
    # Tier 1: Reserve Bank of India
    RSSConnector(
        name="rbi-press",
        url="https://www.rbi.org.in/pressreleasefeed.xml",
        region="in", tier=1, category="monetary",
    ),
    RSSConnector(
        name="rbi-notifications",
        url="https://www.rbi.org.in/notificationfeed.xml",
        region="in", tier=1, category="regulatory",
    ),

    # Tier 2: Major Indian financial media
    RSSConnector(
        name="economic-times-markets",
        url="https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        region="in", tier=2, category="markets",
    ),
    RSSConnector(
        name="economic-times-economy",
        url="https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
        region="in", tier=2, category="economy",
    ),
    RSSConnector(
        name="mint-markets",
        url="https://www.livemint.com/rss/markets",
        region="in", tier=2, category="markets",
    ),
    RSSConnector(
        name="mint-companies",
        url="https://www.livemint.com/rss/companies",
        region="in", tier=2, category="corporate",
    ),
    RSSConnector(
        name="moneycontrol-top",
        url="https://www.moneycontrol.com/rss/MCtopnews.xml",
        region="in", tier=2, category="markets",
    ),
    RSSConnector(
        name="moneycontrol-business",
        url="https://www.moneycontrol.com/rss/business.xml",
        region="in", tier=2, category="corporate",
    ),
    RSSConnector(
        name="business-standard",
        url="https://www.business-standard.com/rss/latest.rss",
        region="in", tier=2, category="markets",
    ),

    # Tier 3: Aggregators
    RSSConnector(
        name="ndtv-profit",
        url="https://feeds.feedburner.com/ndtvprofit-latest",
        region="in", tier=3, category="markets",
    ),
]


US_RSS = [
    # Tier 1: Federal Reserve
    RSSConnector(
        name="fed-monetary",
        url="https://www.federalreserve.gov/feeds/press_monetary.xml",
        region="us", tier=1, category="monetary",
    ),
    RSSConnector(
        name="fed-all-press",
        url="https://www.federalreserve.gov/feeds/press_all.xml",
        region="us", tier=1, category="monetary",
    ),

    # Tier 1: Treasury
    RSSConnector(
        name="us-treasury-press",
        url="https://home.treasury.gov/news/press-releases/feed",
        region="us", tier=1, category="macro",
    ),

    # Tier 1: SEC
    RSSConnector(
        name="sec-press",
        url="https://www.sec.gov/news/pressreleases.rss",
        region="us", tier=1, category="regulatory",
    ),

    # Tier 1: Bureau of Labor Statistics (jobs, CPI)
    RSSConnector(
        name="bls-news",
        url="https://www.bls.gov/feed/news_release.rss",
        region="us", tier=1, category="macro",
    ),
]


EU_RSS = [
    RSSConnector(
        name="ecb-press",
        url="https://www.ecb.europa.eu/rss/press.xml",
        region="eu", tier=1, category="monetary",
    ),
    RSSConnector(
        name="ecb-blog",
        url="https://www.ecb.europa.eu/rss/blog.xml",
        region="eu", tier=1, category="monetary",
    ),
]


UK_RSS = [
    RSSConnector(
        name="boe-news",
        url="https://www.bankofengland.co.uk/rss/news",
        region="uk", tier=1, category="monetary",
    ),
]


JAPAN_RSS = [
    RSSConnector(
        name="boj-news",
        url="https://www.boj.or.jp/en/rss/whatsnew.xml",
        region="jp", tier=1, category="monetary",
    ),
]


# ---------------------------------------------------------------------------
# FRED macro series (US) — requires FRED_API_KEY env var
# ---------------------------------------------------------------------------

FRED_SERIES = [
    FredSeriesConnector(
        name="fred-fed-funds",
        series_id="DFF",
        human_label="US Fed Funds Rate",
        region="us", tier=1, category="monetary",
    ),
    FredSeriesConnector(
        name="fred-10y-yield",
        series_id="DGS10",
        human_label="US 10-Year Treasury Yield",
        region="us", tier=1, category="macro",
    ),
    FredSeriesConnector(
        name="fred-dollar-index",
        series_id="DTWEXBGS",
        human_label="US Trade-Weighted Dollar Index",
        region="us", tier=1, category="macro",
    ),
    FredSeriesConnector(
        name="fred-cpi",
        series_id="CPIAUCSL",
        human_label="US CPI",
        region="us", tier=1, category="macro",
    ),
    FredSeriesConnector(
        name="fred-unemployment",
        series_id="UNRATE",
        human_label="US Unemployment Rate",
        region="us", tier=1, category="macro",
    ),
    FredSeriesConnector(
        name="fred-vix",
        series_id="VIXCLS",
        human_label="CBOE VIX",
        region="us", tier=1, category="markets",
    ),
]


# ---------------------------------------------------------------------------
# yfinance price groups — one connector per logical basket
# ---------------------------------------------------------------------------

YF_PRICES = [
    YFinancePricesConnector(
        name="yf-us-indices",
        tickers=["^GSPC", "^IXIC", "^DJI", "^VIX", "^RUT"],
        region="us", tier=1, category="markets",
    ),
    YFinancePricesConnector(
        name="yf-india-indices",
        tickers=["^NSEI", "^BSESN", "^NSEBANK"],
        region="in", tier=1, category="markets",
    ),
    YFinancePricesConnector(
        name="yf-global-indices",
        tickers=["^FTSE", "^GDAXI", "^N225", "^HSI", "000001.SS"],
        region="global", tier=1, category="markets",
    ),
    YFinancePricesConnector(
        name="yf-commodities",
        tickers=["GC=F", "SI=F", "CL=F", "NG=F", "HG=F"],
        region="global", tier=1, category="commodities",
    ),
    YFinancePricesConnector(
        name="yf-currencies",
        tickers=["DX-Y.NYB", "INR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCNY=X"],
        region="global", tier=1, category="macro",
    ),
    YFinancePricesConnector(
        name="yf-bond-yields",
        tickers=["^TNX", "^IRX", "^TYX"],
        region="us", tier=1, category="macro",
    ),
    YFinancePricesConnector(
        name="yf-crypto",
        tickers=["BTC-USD", "ETH-USD"],
        region="global", tier=2, category="markets",
    ),
    YFinancePricesConnector(
        name="yf-etf-flows",
        # Regional ETFs — price moves hint at capital rotation.
        # SPY=US, QQQ=tech, EEM=EM, INDA=India, FXI=China, EWJ=Japan, EZU=Eurozone
        tickers=["SPY", "QQQ", "EEM", "INDA", "FXI", "EWJ", "EZU"],
        region="global", tier=2, category="capital_flow",
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_connectors() -> list[BaseConnector]:
    """Return every configured connector. Called by the ingestion dispatcher."""
    return [
        *INDIA_RSS,
        *US_RSS,
        *EU_RSS,
        *UK_RSS,
        *JAPAN_RSS,
        *FRED_SERIES,
        *YF_PRICES,
    ]


def get_connectors_by_region(region: str) -> list[BaseConnector]:
    """Filter by source region. Useful for health checks and debug dumps."""
    return [c for c in get_all_connectors() if c.region == region]


def get_connectors_by_category(category: str) -> list[BaseConnector]:
    """Filter by category (monetary, markets, macro, etc)."""
    return [c for c in get_all_connectors() if c.category == category]
