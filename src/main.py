import argparse
import sys

from src.config import MIN_ADV_NOTIONAL, MIN_MARKET_CAP, DEFAULT_TOP_N, DEFAULT_CANDIDATES, SLACK_WEBHOOK_URL
from src.display import console, display_movers
from src.export import export_markdown
from src.filters import apply_liquidity_filters
from src.logger import get_logger, setup_logging
from src.movers import get_movers
from src.news import get_best_news
from src.slack import post_movers_to_slack
from src.summarizer import summarize_catalyst
from src.universe import load_universe

log = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="movers",
        description="Daily stock movers with AI-powered catalyst summaries.",
    )
    p.add_argument("--top", type=int, default=DEFAULT_TOP_N, metavar="N",
                   help=f"Number of movers to display (default: {DEFAULT_TOP_N})")
    p.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES, metavar="N",
                   help=f"Raw movers to fetch before filtering (default: {DEFAULT_CANDIDATES})")
    p.add_argument("--min-mcap", type=float, default=MIN_MARKET_CAP, metavar="$",
                   help=f"Min market cap in dollars (default: {MIN_MARKET_CAP:.0e})")
    p.add_argument("--min-adv", type=float, default=MIN_ADV_NOTIONAL, metavar="$",
                   help=f"Min avg daily volume notional (default: {MIN_ADV_NOTIONAL:.0e})")
    p.add_argument("--gainers", action="store_true", help="Show only gainers")
    p.add_argument("--losers", action="store_true", help="Show only losers")
    p.add_argument("--sector", metavar="SECTOR",
                   help="Filter by GICS sector (e.g. 'Technology', 'Energy', 'Healthcare')")
    p.add_argument("--no-ai", action="store_true", help="Skip AI summarization, show raw headlines")
    p.add_argument("--export", metavar="FILE", help="Export report to markdown file")
    p.add_argument("--slack", action="store_true", help="Post results to Slack via webhook")
    p.add_argument("--refresh", action="store_true", help="Force refresh of ticker universe")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return p


def run(args: argparse.Namespace) -> None:
    setup_logging(verbose=args.verbose)
    log.debug("Starting movers pipeline with args: %s", vars(args))

    # 1. Load universe
    tickers = load_universe(force_refresh=args.refresh)
    log.debug("Universe loaded: %d tickers", len(tickers))

    # 2. Fetch raw movers
    raw = get_movers(tickers, top_n=args.candidates)
    if raw.empty:
        console.print("[red]No price data returned. Market may be closed.[/red]")
        sys.exit(0)
    log.debug("Raw movers fetched: %d", len(raw))

    # 3. Direction filter
    if args.gainers:
        raw = raw[raw["pct_change"] > 0]
        log.debug("After gainers filter: %d", len(raw))
    elif args.losers:
        raw = raw[raw["pct_change"] < 0]
        log.debug("After losers filter: %d", len(raw))

    # 4. Liquidity + sector filter
    filtered = apply_liquidity_filters(
        raw,
        min_mcap=args.min_mcap,
        min_adv=args.min_adv,
        sector=args.sector,
    )
    if filtered.empty:
        msg = "No movers passed liquidity filters"
        if args.sector:
            msg += f" for sector '{args.sector}'"
        console.print(f"[yellow]{msg}.[/yellow]")
        sys.exit(0)

    # 5. Take top N
    top = filtered.head(args.top)
    log.debug("Processing top %d movers", len(top))

    # 6. Fetch news + summarize
    movers = []
    total = len(top)
    for i, (_, row) in enumerate(top.iterrows(), 1):
        ticker = row["ticker"]
        pct = row["pct_change"]
        console.print(f"  [{i}/{total}] {ticker} ({pct:+.1f}%) — fetching news...", end="\r")

        news = get_best_news(ticker)
        log.debug("%s: news headline: %s", ticker, news["headline"][:60])

        catalyst = news["headline"] if args.no_ai else summarize_catalyst(ticker, pct, [news])

        movers.append({
            **row.to_dict(),
            "catalyst": catalyst,
            "news_url": news.get("url", ""),
        })

    console.print(" " * 60, end="\r")  # clear progress line

    # 7. Display
    display_movers(movers)

    # 8. Optional export
    if args.export:
        export_markdown(movers, args.export)
        log.debug("Report exported to %s", args.export)

    # 9. Optional Slack post
    if args.slack:
        webhook = SLACK_WEBHOOK_URL
        if not webhook:
            console.print("[red]SLACK_WEBHOOK_URL not set in .env — skipping Slack post.[/red]")
        else:
            try:
                post_movers_to_slack(movers, webhook)
                console.print("[green]Posted to Slack #dhurley[/green]")
            except Exception as e:
                log.error("Slack post failed: %s", e)
                console.print(f"[red]Slack post failed: {e}[/red]")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
