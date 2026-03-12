import logging
import re

import pandas as pd
import yfinance as yf

from src.fmp import get_gainers_losers
from src.logger import get_logger
from src.skiplist import add_to_skip_list, filter_universe

log = get_logger(__name__)

# Matches yfinance's "possibly delisted" error log lines
_DELISTED_RE = re.compile(r"\$([A-Z\-]+).*?possibly delisted", re.IGNORECASE)


class _DelistedCapture(logging.Handler):
    """Intercepts yfinance log messages to capture delisted ticker symbols."""
    def __init__(self):
        super().__init__()
        self.delisted: set[str] = set()

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        for match in _DELISTED_RE.finditer(msg):
            self.delisted.add(match.group(1))


def _get_movers_yfinance(tickers: list[str], top_n: int) -> pd.DataFrame:
    """Primary: fetch price data via yfinance, capturing delisted tickers."""
    # Attach capture handler to yfinance's logger
    yf_log = logging.getLogger("yfinance")
    capture = _DelistedCapture()
    yf_log.addHandler(capture)

    try:
        data = yf.download(
            tickers,
            period="5d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
        )
    finally:
        yf_log.removeHandler(capture)

    # Persist any explicitly delisted tickers
    if capture.delisted:
        add_to_skip_list(list(capture.delisted))

    results = []
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                closes = data["Close"].dropna()
                volumes = data["Volume"].dropna()
            else:
                closes = data[ticker]["Close"].dropna()
                volumes = data[ticker]["Volume"].dropna()

            if len(closes) < 2:
                continue

            prev = float(closes.iloc[-2])
            curr = float(closes.iloc[-1])
            if prev == 0:
                continue

            pct = (curr - prev) / prev * 100
            volume = float(volumes.iloc[-1]) if len(volumes) > 0 else 0

            results.append({
                "ticker": ticker,
                "price": round(curr, 2),
                "prev_close": round(prev, 2),
                "pct_change": round(pct, 2),
                "volume": volume,
            })
        except Exception:
            continue

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df["abs_pct"] = df["pct_change"].abs()
    df = df.sort_values("abs_pct", ascending=False).drop(columns="abs_pct")
    return df.head(top_n).reset_index(drop=True)


def _get_movers_fmp(tickers: list[str], top_n: int) -> pd.DataFrame:
    """Fallback: fetch top gainers/losers from FMP, filtered to our universe."""
    log.warning("yfinance returned no data — falling back to FMP gainers/losers")
    print("  yfinance returned no data, falling back to FMP...")
    universe = set(tickers)
    df = get_gainers_losers(universe=universe)
    if df.empty:
        return df
    return df.head(top_n).reset_index(drop=True)


def get_movers(tickers: list[str], top_n: int = 50) -> pd.DataFrame:
    """Fetch top movers by % change.

    Filters out previously flagged delisted tickers, tries yfinance first,
    falls back to FMP gainers/losers if yfinance fails.
    """
    tickers = filter_universe(tickers)
    print(f"Fetching price data for {len(tickers)} tickers...")

    df = _get_movers_yfinance(tickers, top_n)

    if df.empty:
        df = _get_movers_fmp(tickers, top_n)

    if df.empty:
        log.error("Both yfinance and FMP returned no data")

    return df
