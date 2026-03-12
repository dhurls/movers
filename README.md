# Stock Movers Intelligence Tool

A CLI tool for prop traders that surfaces the day's biggest liquid US equity movers alongside AI-generated catalyst summaries.

## What It Does

Each run:
1. Fetches price data for ~500 S&P 500 tickers via yfinance
2. Filters to liquid, institutional-grade names (>$2B market cap, >$100M ADV)
3. Fetches the latest news for each mover via Finnhub and MarketAux
4. Summarizes the catalyst in one sentence using Claude (Anthropic API)
5. Renders a color-coded terminal table

## Setup

### 1. Install dependencies

```bash
pip install yfinance pandas requests rich anthropic python-dotenv lxml
```

### 2. Configure API keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```
FINNHUB_API_KEY=your_finnhub_key        # finnhub.io — free tier
MARKETAUX_API_KEY=your_marketaux_key    # marketaux.com — free tier (100 req/day)
ANTHROPIC_API_KEY=your_anthropic_key    # console.anthropic.com
```

### 3. Run

```bash
python -m src.main
```

## Usage

```
python -m src.main [options]

Options:
  --top N          Number of movers to display (default: 20)
  --candidates N   Raw movers to fetch before filtering (default: 100)
  --min-mcap $     Minimum market cap in dollars (default: 2e9)
  --min-adv $      Minimum avg daily volume notional (default: 1e8)
  --gainers        Show only gainers
  --losers         Show only losers
  --sector SECTOR  Filter by GICS sector (e.g. Technology, Energy, Healthcare)
  --no-ai          Skip AI summarization, show raw headlines instead
  --export FILE    Export report to a markdown file
  --refresh        Force-refresh the ticker universe
  --verbose        Enable debug logging
```

### Examples

```bash
# Top 10 movers
python -m src.main --top 10

# Only gainers in Energy
python -m src.main --gainers --sector Energy

# Fast run without Claude (raw headlines)
python -m src.main --no-ai

# Export to markdown
python -m src.main --export movers_report.md

# Debug mode
python -m src.main --top 5 --verbose
```

## Architecture

```
Universe (~500 tickers)
    └─ get_movers()        # yfinance: 5-day price fetch, compute % change
        └─ apply_filters() # market cap + ADV + sector (SQLite cache)
            └─ get_best_news()    # Finnhub → MarketAux fallback
                └─ summarize_catalyst()  # Claude claude-opus-4-6
                    └─ display_movers()  # rich terminal table
```

## Data Sources & Rate Limits

| Source      | Use                        | Free Tier Limit          |
|-------------|----------------------------|--------------------------|
| yfinance    | Price data, ticker metadata | Unofficial, no hard limit |
| Finnhub     | Company news               | 60 calls/min             |
| MarketAux   | News fallback              | 100 calls/day            |
| Claude API  | Catalyst summarization     | Pay-per-use (~$0.05/run) |

## Cost

A typical run (20 movers) uses ~30 Claude API calls with ~300 input + 50 output tokens each.
At Opus pricing: **~$0.05–0.10 per run**.
