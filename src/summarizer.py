import anthropic

from src.config import ANTHROPIC_API_KEY
from src.logger import get_logger
from src.retry import with_retry

log = get_logger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


@with_retry(max_attempts=3, base_delay=2.0, exceptions=(anthropic.APIStatusError, anthropic.APIConnectionError))
def _call_api(ticker: str, pct_change: float, news_text: str) -> str:
    direction = "up" if pct_change > 0 else "down"
    response = _get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": (
                f"You are a prop trading desk analyst. {ticker} is {direction} "
                f"{abs(pct_change):.1f}% today.\n\n"
                f"News:\n{news_text}\n\n"
                "Write ONE concise sentence explaining the catalyst for the move. "
                "Be specific — name the event, number, or development. "
                "If no clear catalyst exists, say: "
                "'No clear catalyst identified — likely technical or flow-driven.'"
            ),
        }],
    )
    return response.content[0].text.strip()


def summarize_catalyst(ticker: str, pct_change: float, articles: list[dict]) -> str:
    """Produce a 1-sentence catalyst summary for a ticker's move using Claude."""
    if not articles or all(a.get("headline") == "No news found" for a in articles):
        return "No clear catalyst identified — likely technical or flow-driven."

    news_text = "\n".join(
        f"- {a['headline']}: {a.get('summary', '')}"
        for a in articles
        if a.get("headline") and a["headline"] != "No news found"
    )

    try:
        result = _call_api(ticker, pct_change, news_text)
        log.debug("%s: catalyst: %s", ticker, result)
        return result
    except Exception as e:
        log.error("%s: summarization failed: %s", ticker, e)
        return "No clear catalyst identified — likely technical or flow-driven."
