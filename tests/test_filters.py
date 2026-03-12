import pandas as pd
import pytest

from src.cache import get_meta, set_meta
from src.filters import apply_liquidity_filters


def _make_df(rows):
    return pd.DataFrame(rows)


def test_filter_passes_large_caps(tmp_path, monkeypatch):
    """Tickers that meet both thresholds should pass."""
    monkeypatch.setenv("CACHE_DB", str(tmp_path / "test.db"))

    import src.filters as f

    def fake_fetch(ticker):
        return {"market_cap": 5_000_000_000, "avg_volume": 10_000_000, "short_name": ticker, "exchange": "NMS"}

    monkeypatch.setattr(f, "_fetch_meta", fake_fetch)

    df = _make_df([
        {"ticker": "AAPL", "price": 180.0, "prev_close": 175.0, "pct_change": 2.8, "volume": 80_000_000},
        {"ticker": "MSFT", "price": 400.0, "prev_close": 390.0, "pct_change": 2.5, "volume": 30_000_000},
    ])
    result = apply_liquidity_filters(df, min_mcap=2e9, min_adv=1e8)
    assert set(result["ticker"]) == {"AAPL", "MSFT"}


def test_filter_blocks_small_caps(tmp_path, monkeypatch):
    """Tickers below market cap threshold should be dropped."""
    import src.filters as f

    def fake_fetch(ticker):
        return {"market_cap": 500_000_000, "avg_volume": 5_000_000, "short_name": ticker, "exchange": "NMS"}

    monkeypatch.setattr(f, "_fetch_meta", fake_fetch)

    df = _make_df([
        {"ticker": "TINY", "price": 10.0, "prev_close": 9.0, "pct_change": 11.0, "volume": 1_000_000},
    ])
    result = apply_liquidity_filters(df, min_mcap=2e9, min_adv=1e8)
    assert result.empty


def test_filter_blocks_low_adv(tmp_path, monkeypatch):
    """Tickers with large mcap but thin volume should be dropped."""
    import src.filters as f

    def fake_fetch(ticker):
        return {"market_cap": 10_000_000_000, "avg_volume": 50_000, "short_name": ticker, "exchange": "NMS"}

    monkeypatch.setattr(f, "_fetch_meta", fake_fetch)

    df = _make_df([
        {"ticker": "ILLIQ", "price": 500.0, "prev_close": 480.0, "pct_change": 4.2, "volume": 50_000},
    ])
    result = apply_liquidity_filters(df, min_mcap=2e9, min_adv=1e8)
    assert result.empty


def test_filter_adds_metadata_columns(monkeypatch):
    """Filtered rows should have company_name, market_cap, adv_notional columns."""
    import src.filters as f

    def fake_fetch(ticker):
        return {"market_cap": 3e9, "avg_volume": 2_000_000, "short_name": "Big Co", "exchange": "NMS"}

    monkeypatch.setattr(f, "_fetch_meta", fake_fetch)

    df = _make_df([
        {"ticker": "BIG", "price": 60.0, "prev_close": 55.0, "pct_change": 9.1, "volume": 2_000_000},
    ])
    result = apply_liquidity_filters(df, min_mcap=2e9, min_adv=1e8)
    assert "company_name" in result.columns
    assert "market_cap" in result.columns
    assert "adv_notional" in result.columns
    assert result.iloc[0]["company_name"] == "Big Co"


def test_cache_roundtrip():
    """set_meta / get_meta should store and retrieve data correctly."""
    set_meta("TEST", {"market_cap": 1e10, "avg_volume": 5e6, "short_name": "Test Co", "exchange": "NMS"})
    meta = get_meta("TEST")
    assert meta is not None
    assert meta["market_cap"] == 1e10
    assert meta["short_name"] == "Test Co"
