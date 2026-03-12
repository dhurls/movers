import time
from datetime import date

import requests

from src.config import FINNHUB_API_KEY, FINNHUB_BASE_URL, MARKETAUX_API_KEY, MARKETAUX_BASE_URL
from src.logger import get_logger
from src.retry import with_retry

log = get_logger(__name__)


@with_retry(max_attempts=3, base_delay=1.0, exceptions=(requests.RequestException,))
def _get(url: str, params: dict) -> requests.Response:
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp


def fetch_finnhub_news(ticker: str, api_key: str = FINNHUB_API_KEY) -> list[dict]:
    """Fetch today's news for a ticker from Finnhub."""
    today = date.today().isoformat()
    try:
        resp = _get(
            f"{FINNHUB_BASE_URL}/company-news",
            {"symbol": ticker, "from": today, "to": today, "token": api_key},
        )
        articles = resp.json()
        if not isinstance(articles, list):
            return []
        articles.sort(key=lambda x: x.get("datetime", 0), reverse=True)
        result = [
            {
                "headline": a.get("headline", ""),
                "summary": a.get("summary", ""),
                "url": a.get("url", ""),
                "source": a.get("source", "Finnhub"),
            }
            for a in articles[:3]
            if a.get("headline")
        ]
        log.debug("%s: Finnhub returned %d articles", ticker, len(result))
        return result
    except Exception as e:
        log.warning("%s: Finnhub news failed: %s", ticker, e)
        return []


def fetch_marketaux_news(ticker: str, api_key: str = MARKETAUX_API_KEY) -> list[dict]:
    """Fetch news for a ticker from MarketAux."""
    try:
        resp = _get(
            f"{MARKETAUX_BASE_URL}/news/all",
            {"symbols": ticker, "filter_entities": "true", "language": "en", "api_token": api_key},
        )
        data = resp.json()
        articles = data.get("data", [])
        result = [
            {
                "headline": a.get("title", ""),
                "summary": a.get("description", ""),
                "url": a.get("url", ""),
                "source": a.get("source", "MarketAux"),
            }
            for a in articles[:3]
            if a.get("title")
        ]
        log.debug("%s: MarketAux returned %d articles", ticker, len(result))
        return result
    except Exception as e:
        log.warning("%s: MarketAux news failed: %s", ticker, e)
        return []


def _dedupe(articles: list[dict]) -> list[dict]:
    """Remove near-duplicate headlines (exact match on first 60 chars)."""
    seen = set()
    unique = []
    for a in articles:
        key = a["headline"][:60].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def get_best_news(
    ticker: str,
    finnhub_key: str = FINNHUB_API_KEY,
    marketaux_key: str = MARKETAUX_API_KEY,
    delay: float = 0.5,
) -> dict:
    """Return the best available news for a ticker.

    Tries Finnhub first; falls back to MarketAux if Finnhub returns nothing.
    """
    articles = fetch_finnhub_news(ticker, finnhub_key)
    time.sleep(delay)

    if not articles:
        log.debug("%s: falling back to MarketAux", ticker)
        articles = fetch_marketaux_news(ticker, marketaux_key)
        time.sleep(delay)

    articles = _dedupe(articles)

    if articles:
        return articles[0]

    log.debug("%s: no news found from any source", ticker)
    return {"headline": "No news found", "summary": "", "url": "", "source": ""}
