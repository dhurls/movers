import io
import json
import os
from datetime import datetime, timedelta

import pandas as pd
import requests

from src.config import TICKERS_FILE, UNIVERSE_REFRESH_DAYS


def _fetch_sp500() -> list[str]:
    """Scrape S&P 500 tickers from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = tables[0]
    tickers = df["Symbol"].tolist()
    # Wikipedia uses dots (BRK.B) — Yahoo uses dashes (BRK-B)
    return [t.replace(".", "-") for t in tickers]


def _fetch_ishares_csv(product_url: str) -> list[str]:
    """Download an iShares ETF holdings CSV and return a list of equity tickers."""
    try:
        resp = requests.get(
            product_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        # iShares CSVs have a few header rows before the actual data
        text = resp.text
        # Find the line that starts the real table (has "Ticker" as a column)
        lines = text.splitlines()
        header_idx = next(
            (i for i, l in enumerate(lines) if l.startswith('"Ticker"') or l.startswith("Ticker")),
            None,
        )
        if header_idx is None:
            return []
        csv_text = "\n".join(lines[header_idx:])
        df = pd.read_csv(io.StringIO(csv_text))
        col = next((c for c in df.columns if c.strip().lower() == "ticker"), None)
        if col is None:
            return []
        tickers = df[col].dropna().astype(str).tolist()
        # Keep only simple alphabetic tickers (drop cash, futures, etc.)
        return [t.strip() for t in tickers if t.strip().isalpha()]
    except Exception:
        return []


def _fetch_russell2000() -> list[str]:
    """Fetch Russell 2000 tickers from iShares IWM ETF holdings CSV."""
    url = (
        "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
        "1467271812596.ajax?tab=holdings&fileType=csv"
    )
    return _fetch_ishares_csv(url)


def _is_stale(filepath: str, days: int) -> bool:
    if not os.path.exists(filepath):
        return True
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    return datetime.now() - mtime > timedelta(days=days)


def refresh_universe() -> list[str]:
    """Fetch S&P 500 + Russell 2000, dedupe, save to tickers.json. Returns ticker list."""
    print("Refreshing ticker universe...")

    sp500 = _fetch_sp500()
    print(f"  S&P 500: {len(sp500)} tickers")

    r2000 = _fetch_russell2000()
    print(f"  Russell 2000: {len(r2000)} tickers")

    combined = sorted(set(sp500 + r2000))
    print(f"  Combined (deduped): {len(combined)} tickers")

    os.makedirs(os.path.dirname(TICKERS_FILE), exist_ok=True)
    with open(TICKERS_FILE, "w") as f:
        json.dump({"updated_at": datetime.now().isoformat(), "tickers": combined}, f)

    return combined


def load_universe(force_refresh: bool = False) -> list[str]:
    """Load tickers from file, refreshing if stale or forced."""
    if force_refresh or _is_stale(TICKERS_FILE, UNIVERSE_REFRESH_DAYS):
        return refresh_universe()

    with open(TICKERS_FILE) as f:
        data = json.load(f)

    tickers = data.get("tickers", [])
    updated = data.get("updated_at", "unknown")
    print(f"Loaded {len(tickers)} tickers (universe last updated {updated[:10]})")
    return tickers
