from unittest.mock import MagicMock, patch

from src.summarizer import summarize_catalyst


def _mock_response(text: str):
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_summarize_returns_string(monkeypatch):
    articles = [{"headline": "AAPL beats Q1 earnings", "summary": "Apple beat EPS by $0.10"}]
    with patch("src.summarizer._get_client") as mock_client:
        mock_client.return_value.messages.create.return_value = _mock_response(
            "Apple surged after reporting Q1 EPS of $2.40, beating consensus by $0.10."
        )
        result = summarize_catalyst("AAPL", 5.2, articles)
    assert isinstance(result, str)
    assert len(result) > 0


def test_summarize_no_news_returns_default():
    articles = [{"headline": "No news found", "summary": "", "url": "", "source": ""}]
    result = summarize_catalyst("XYZ", -3.1, articles)
    assert "No clear catalyst" in result


def test_summarize_empty_articles_returns_default():
    result = summarize_catalyst("ABC", 2.0, [])
    assert "No clear catalyst" in result


def test_summarize_calls_api_with_ticker(monkeypatch):
    articles = [{"headline": "DOW rallies on tariff news", "summary": "Tariff truce announced"}]
    with patch("src.summarizer._get_client") as mock_client:
        mock_create = mock_client.return_value.messages.create
        mock_create.return_value = _mock_response("DOW surged on US-China tariff truce.")

        result = summarize_catalyst("DOW", 9.1, articles)

        call_args = mock_create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "DOW" in prompt
        assert "9.1" in prompt
