import pytest

from src.news import _dedupe, fetch_finnhub_news, fetch_marketaux_news, get_best_news


FAKE_FINNHUB = [
    {"headline": "AAPL beats earnings", "summary": "Apple reported...", "url": "http://a.com", "source": "Reuters"},
    {"headline": "Apple unveils new Mac", "summary": "At WWDC...", "url": "http://b.com", "source": "Bloomberg"},
]

FAKE_MARKETAUX = [
    {"headline": "Apple stock surges", "summary": "Shares rose...", "url": "http://c.com", "source": "MarketAux"},
]


def test_get_best_news_prefers_finnhub(monkeypatch):
    import src.news as n
    monkeypatch.setattr(n, "fetch_finnhub_news", lambda t, k=None: FAKE_FINNHUB)
    monkeypatch.setattr(n, "fetch_marketaux_news", lambda t, k=None: FAKE_MARKETAUX)
    monkeypatch.setattr(n.time, "sleep", lambda _: None)

    result = get_best_news("AAPL")
    assert result["headline"] == "AAPL beats earnings"
    assert result["source"] == "Reuters"


def test_get_best_news_falls_back_to_marketaux(monkeypatch):
    import src.news as n
    monkeypatch.setattr(n, "fetch_finnhub_news", lambda t, k=None: [])
    monkeypatch.setattr(n, "fetch_marketaux_news", lambda t, k=None: FAKE_MARKETAUX)
    monkeypatch.setattr(n.time, "sleep", lambda _: None)

    result = get_best_news("AAPL")
    assert result["headline"] == "Apple stock surges"


def test_get_best_news_no_articles(monkeypatch):
    import src.news as n
    monkeypatch.setattr(n, "fetch_finnhub_news", lambda t, k=None: [])
    monkeypatch.setattr(n, "fetch_marketaux_news", lambda t, k=None: [])
    monkeypatch.setattr(n.time, "sleep", lambda _: None)

    result = get_best_news("AAPL")
    assert result["headline"] == "No news found"


def test_dedupe_removes_duplicates():
    # Two articles share identical first 60 chars (exact duplicate headline)
    shared = "Apple beats Q1 earnings estimates by wide margin, shares jump"
    articles = [
        {"headline": shared, "summary": "Source A", "url": "http://a.com", "source": "Reuters"},
        {"headline": shared, "summary": "Source B", "url": "http://b.com", "source": "Bloomberg"},
        {"headline": "Completely different headline here", "summary": "", "url": "", "source": ""},
    ]
    result = _dedupe(articles)
    assert len(result) == 2


def test_finnhub_handles_api_error(monkeypatch):
    import requests
    import src.news as n

    def bad_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError("timeout")

    monkeypatch.setattr(requests, "get", bad_get)
    result = fetch_finnhub_news("AAPL", api_key="fake")
    assert result == []


def test_marketaux_handles_api_error(monkeypatch):
    import requests
    import src.news as n

    def bad_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError("timeout")

    monkeypatch.setattr(requests, "get", bad_get)
    result = fetch_marketaux_news("AAPL", api_key="fake")
    assert result == []
