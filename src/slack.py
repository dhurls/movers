from datetime import date

import requests

from src.logger import get_logger

log = get_logger(__name__)


def post_movers_to_slack(movers: list[dict], webhook_url: str) -> None:
    """Post today's top movers as a formatted Slack message."""
    date_str = date.today().strftime("%B %d, %Y")

    lines = [f":chart_with_upwards_trend: *Today's Top Movers — {date_str}*\n"]

    for row in movers:
        ticker = row["ticker"]
        pct = row["pct_change"]
        price = row["price"]
        catalyst = row.get("catalyst", "")
        arrow = ":green_circle:" if pct > 0 else ":red_circle:"
        lines.append(f"{arrow} *{ticker}* {pct:+.1f}% (${price:.2f}) — {catalyst}")

    text = "\n".join(lines)

    resp = requests.post(webhook_url, json={"text": text}, timeout=10)
    resp.raise_for_status()
    log.debug("Slack post succeeded: %s", resp.status_code)
