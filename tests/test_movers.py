import pandas as pd
import pytest

from src.movers import get_movers


def test_get_movers_returns_dataframe():
    tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    df = get_movers(tickers, top_n=5)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_get_movers_columns():
    tickers = ["AAPL", "MSFT", "TSLA"]
    df = get_movers(tickers, top_n=3)
    expected_cols = {"ticker", "price", "prev_close", "pct_change", "volume"}
    assert expected_cols.issubset(set(df.columns))


def test_get_movers_sorted_by_abs_pct():
    tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "GOOGL", "META"]
    df = get_movers(tickers, top_n=7)
    abs_pcts = df["pct_change"].abs().tolist()
    assert abs_pcts == sorted(abs_pcts, reverse=True)


def test_get_movers_respects_top_n():
    tickers = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]
    df = get_movers(tickers, top_n=3)
    assert len(df) <= 3


def test_get_movers_invalid_tickers_skipped():
    tickers = ["AAPL", "FAKE_TICKER_XYZ123", "MSFT"]
    df = get_movers(tickers, top_n=10)
    assert "FAKE_TICKER_XYZ123" not in df["ticker"].values
    assert len(df) >= 1
