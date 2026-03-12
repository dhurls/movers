from datetime import date


def export_markdown(movers: list[dict], filepath: str = "movers_report.md") -> None:
    """Export movers report to a markdown file."""
    with open(filepath, "w") as f:
        f.write(f"# Daily Movers Report — {date.today()}\n\n")
        for m in movers:
            emoji = "🟢" if m["pct_change"] > 0 else "🔴"
            mcap = m.get("market_cap", 0)
            mcap_str = f"${mcap / 1e9:.1f}B" if mcap >= 1e9 else f"${mcap / 1e6:.0f}M"
            f.write(f"## {emoji} {m['ticker']} ({m['pct_change']:+.1f}%)\n")
            f.write(f"**{m.get('company_name', m['ticker'])}** | ${m['price']:.2f} | MCap: {mcap_str}\n\n")
            f.write(f"**Catalyst:** {m.get('catalyst', '—')}\n\n")
            if m.get("news_url"):
                f.write(f"[Source]({m['news_url']})\n\n")
            f.write("---\n\n")
    print(f"Report saved to {filepath}")
