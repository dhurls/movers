from datetime import date

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def display_movers(movers: list[dict]) -> None:
    """Render the movers list as a rich terminal table."""
    table = Table(
        title=f"Today's Movers — Liquid Names  ({date.today()})",
        show_lines=True,
        highlight=True,
    )

    table.add_column("Ticker", style="bold cyan", width=8, no_wrap=True)
    table.add_column("Name", width=22, no_wrap=True)
    table.add_column("% Chg", justify="right", width=8)
    table.add_column("Price", justify="right", width=9)
    table.add_column("Mkt Cap", justify="right", width=9)
    table.add_column("Catalyst", width=58)

    for m in movers:
        pct = m["pct_change"]
        color = "green" if pct > 0 else "red"
        pct_text = Text(f"{pct:+.1f}%", style=color)

        mcap = m.get("market_cap", 0)
        mcap_str = f"${mcap / 1e9:.1f}B" if mcap >= 1e9 else f"${mcap / 1e6:.0f}M"

        table.add_row(
            m["ticker"],
            m.get("company_name", m["ticker"])[:22],
            pct_text,
            f"${m['price']:.2f}",
            mcap_str,
            m.get("catalyst", "—"),
        )

    console.print(table)
