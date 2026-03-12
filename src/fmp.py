"""FinancialModelingPrep API integration — backup price data source."""

import requests
import pandas as pd

from src.config import FMP_API_KEY, FMP_STABLE_URL
from src.logger import get_logger
from src.retry import with_retry

log = get_logger(__name__)


@with_retry(max_attempts=3, base_delay=1.0, exceptions=(requests.RequestException,))
def _get(endpoint: str) -> list | dict:
    resp = requests.get(
        f"{FMP_STABLE_URL}/{endpoint}",
        params={"apikey": FMP_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_items(items: list, universe: set[str] | None) -> list[dict]:
    rows = []
    for item in items:
        ticker = item.get("symbol", "")
        if not ticker:
            continue
        if universe and ticker not in universe:
            continue
        price = float(item.get("price", 0) or 0)
        change = float(item.get("change", 0) or 0)
        pct = float(item.get("changesPercentage", 0) or 0)
        prev = round(price - change, 2) if price else 0
        rows.append({
            "ticker": ticker,
            "price": round(price, 2),
            "prev_close": prev,
            "pct_change": round(pct, 2),
            "volume": float(item.get("volume", 0) or 0),
        })
    return rows


def get_gainers_losers(universe: set[str] | None = None) -> pd.DataFrame:
    """Fetch top gainers and losers from FMP stable API.

    If a universe set is provided, results are filtered to only those tickers.
    Returns a DataFrame sorted by absolute % change descending.
    """
    results = []
    for endpoint in ("biggest-gainers", "biggest-losers"):
        try:
            data = _get(endpoint)
            if not isinstance(data, list):
                log.warning("FMP %s returned unexpected type: %s", endpoint, type(data))
                continue
            rows = _parse_items(data, universe)
            log.debug("FMP %s: %d items (%d in universe)", endpoint, len(data), len(rows))
            results.extend(rows)
        except Exception as e:
            log.warning("FMP %s failed: %s", endpoint, e)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df["abs_pct"] = df["pct_change"].abs()
    df = df.sort_values("abs_pct", ascending=False).drop(columns="abs_pct")
    return df.reset_index(drop=True)
