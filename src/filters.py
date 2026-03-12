import time

import pandas as pd
import yfinance as yf

from src.cache import get_meta, set_meta
from src.config import MIN_ADV_NOTIONAL, MIN_MARKET_CAP
from src.logger import get_logger
from src.retry import with_retry

log = get_logger(__name__)


@with_retry(max_attempts=3, base_delay=1.0, exceptions=(Exception,))
def _fetch_info(ticker: str) -> dict:
    return yf.Ticker(ticker).info


def _fetch_meta(ticker: str) -> dict | None:
    """Fetch ticker metadata from cache or yfinance."""
    cached = get_meta(ticker)
    if cached:
        log.debug("%s: cache hit", ticker)
        return cached

    try:
        log.debug("%s: fetching from yfinance", ticker)
        info = _fetch_info(ticker)
        market_cap = info.get("marketCap") or 0
        avg_volume = info.get("averageVolume") or 0
        short_name = info.get("shortName") or ticker
        exchange = info.get("exchange") or ""
        sector = info.get("sector") or ""

        meta = {
            "market_cap": market_cap,
            "avg_volume": avg_volume,
            "short_name": short_name,
            "exchange": exchange,
            "sector": sector,
        }
        set_meta(ticker, meta)
        return meta
    except Exception as e:
        log.warning("%s: failed to fetch metadata: %s", ticker, e)
        return None


def apply_liquidity_filters(
    df: pd.DataFrame,
    min_mcap: float = MIN_MARKET_CAP,
    min_adv: float = MIN_ADV_NOTIONAL,
    sector: str | None = None,
) -> pd.DataFrame:
    """Filter movers to liquid institutional-grade names.

    Keeps tickers with:
      - Market cap >= min_mcap (default $2B)
      - Average daily volume notional >= min_adv (default $100M)
      - Optionally: sector matches the given sector string (case-insensitive)
    """
    total = len(df)
    log.debug("Applying filters to %d movers (mcap>=%.0e, adv>=%.0e, sector=%s)",
              total, min_mcap, min_adv, sector or "any")
    print(f"Applying liquidity filters to {total} movers...")

    filtered = []
    for _, row in df.iterrows():
        ticker = row["ticker"]
        meta = _fetch_meta(ticker)
        if meta is None:
            continue

        market_cap = meta.get("market_cap") or 0
        avg_volume = meta.get("avg_volume") or 0
        avg_price = row["price"]
        adv_notional = avg_volume * avg_price
        ticker_sector = (meta.get("sector") or "").lower()

        if market_cap < min_mcap:
            log.debug("%s: dropped — mcap $%.0fB < threshold", ticker, market_cap / 1e9)
            continue
        if adv_notional < min_adv:
            log.debug("%s: dropped — ADV $%.0fM < threshold", ticker, adv_notional / 1e6)
            continue
        if sector and sector.lower() not in ticker_sector:
            log.debug("%s: dropped — sector '%s' != '%s'", ticker, ticker_sector, sector)
            continue

        row = row.copy()
        row["market_cap"] = market_cap
        row["adv_notional"] = adv_notional
        row["company_name"] = meta.get("short_name") or ticker
        row["sector"] = meta.get("sector") or ""
        filtered.append(row)

        time.sleep(0.1)

    result = pd.DataFrame(filtered).reset_index(drop=True)
    print(f"  {len(result)}/{total} passed filters")
    return result
