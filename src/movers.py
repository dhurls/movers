import logging
import re
import time

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


_DOWNLOAD_CHUNK_SIZE = 500
_DOWNLOAD_CHUNK_PAUSE = 30  # seconds between chunks


def _download_chunk(tickers: list[str], capture: "_DelistedCapture") -> pd.DataFrame:
    """Download price data for a single chunk of tickers."""
    return yf.download(
        tickers,
        period="5d",
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=True,
    )


def _get_movers_yfinance(tickers: list[str], top_n: int) -> pd.DataFrame:
    """Primary: fetch price data via yfinance in chunks to avoid rate limiting."""
    yf_log = logging.getLogger("yfinance")
    capture = _DelistedCapture()
    yf_log.addHandler(capture)

    chunks = [tickers[i:i + _DOWNLOAD_CHUNK_SIZE] for i in range(0, len(tickers), _DOWNLOAD_CHUNK_SIZE)]
    all_results = []

    try:
        for idx, chunk in enumerate(chunks):
            if idx > 0:
                print(f"  Pausing {_DOWNLOAD_CHUNK_PAUSE}s between download chunks ({idx}/{len(chunks)})...")
                time.sleep(_DOWNLOAD_CHUNK_PAUSE)

            data = _download_chunk(chunk, capture)

            for ticker in chunk:
                try:
                    if len(chunk) == 1:
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

                    all_results.append({
                        "ticker": ticker,
                        "price": round(curr, 2),
                        "prev_close": round(prev, 2),
                        "pct_change": round(pct, 2),
                        "volume": volume,
                    })
                except Exception:
                    continue
    finally:
        yf_log.removeHandler(capture)

    # Persist any explicitly delisted tickers
    if capture.delisted:
        add_to_skip_list(list(capture.delisted))

    if not all_results:
        return pd.DataFrame()

    df = pd.DataFrame(all_results)
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
