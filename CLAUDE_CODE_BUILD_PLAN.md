# Stock Movers Intelligence Tool — Claude Code Build Plan

## What This Is

A CLI tool (with optional TUI) that a prop trader runs each morning (or intraday) to get:

1. **Today's biggest % movers** in liquid US equities (>$2B mkt cap, >$100M ADV)
2. **The news / catalyst** driving each move, auto-fetched and summarized

The output is a ranked table: ticker, % change, market cap, ADV, headline, source URL, and a 1-sentence AI summary of the catalyst.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                     CLI / TUI                        │
│  (rich table output, optional textual TUI)          │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────▼────────┐
       │  Orchestrator   │  ← main pipeline
       └───┬────┬────┬──┘
           │    │    │
     ┌─────▼┐ ┌▼────▼─────┐ ┌──────────────┐
     │Movers│ │  Filters   │ │ News Fetcher │
     │ API  │ │ (mcap/ADV) │ │ + Summarizer │
     └──────┘ └────────────┘ └──────────────┘
```

---

## Phase 1: Price Movers Ingestion

### Goal
Get the day's top gainers and losers across US exchanges.

### API Strategy (free tier, no payment required)

**Primary: Yahoo Finance via `yfinance` (Python)**
- No API key needed. Completely free.
- Use the **screener** module or scrape the Yahoo Finance gainers/losers endpoint.
- Specifically: `yfinance` doesn't have a native "top movers" endpoint, so use the undocumented Yahoo screener API that `yfinance` wraps.
- Fallback approach: maintain a universe list (e.g. S&P 500 + Russell 1000 tickers) and batch-fetch daily quotes to compute % change yourself.

**Secondary / Validation: Finnhub `/stock/market-status` + `/quote`**
- Finnhub free tier: 60 calls/min.
- No native "top movers" list on free tier, but you can batch `/quote` calls against your universe.
- Useful for validating Yahoo data and getting real-time quotes during market hours.

**Tertiary (if you want a pre-built movers list): Polygon.io free tier**
- `GET /v2/snapshot/locale/us/markets/stocks/gainers` and `/losers`
- Free tier: 5 calls/min, delayed data. Good enough for EOD screening.
- Requires free API key signup.

### Recommended Approach

Use a **hybrid strategy**:

```
1. Maintain a static universe file: S&P 500 + Russell 1000 tickers (~1,500 names)
   - Refresh monthly from Wikipedia or a free index composition API
   - Store as tickers.json

2. Batch-fetch daily price data via yfinance:
   - yfinance.download(tickers, period="2d") → gives yesterday close + today close
   - Compute pct_change for each ticker
   - This is ~1,500 tickers in one bulk call — yfinance handles batching internally

3. Sort by abs(pct_change) descending → raw movers list
```

### Implementation Notes

```python
# Core data fetch — this is the heart of Phase 1
import yfinance as yf
import pandas as pd

def get_movers(tickers: list[str], top_n: int = 50) -> pd.DataFrame:
    """Fetch 2-day price history, compute % change, return top movers."""
    data = yf.download(tickers, period="5d", group_by="ticker", threads=True)
    # Use 5d to handle weekends/holidays — take last 2 trading days

    results = []
    for ticker in tickers:
        try:
            closes = data[ticker]["Close"].dropna()
            if len(closes) < 2:
                continue
            prev = closes.iloc[-2]
            curr = closes.iloc[-1]
            pct = (curr - prev) / prev * 100
            volume = data[ticker]["Volume"].iloc[-1]
            results.append({
                "ticker": ticker,
                "price": curr,
                "prev_close": prev,
                "pct_change": pct,
                "volume": volume,
            })
        except Exception:
            continue

    df = pd.DataFrame(results)
    df["abs_pct"] = df["pct_change"].abs()
    df = df.sort_values("abs_pct", ascending=False)
    return df.head(top_n)
```

---

## Phase 2: Liquidity Filters

### Goal
Filter the raw movers list down to only liquid, institutional-grade names.

### Filter Criteria
| Filter        | Threshold        | Data Source                |
|---------------|------------------|----------------------------|
| Market Cap    | > $2B            | yfinance `.info["marketCap"]` or Finnhub `/stock/profile2` |
| Avg Daily Vol | > $100M notional | Compute: 20-day avg volume × avg price |
| Exchange      | NYSE, NASDAQ     | Drop OTC / pink sheets    |
| Asset Type    | Common stock     | Drop ETFs, ADRs, warrants, SPACs (optional) |

### Implementation Notes

```python
def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply market cap and ADV filters to movers list."""
    filtered = []
    for _, row in df.iterrows():
        try:
            info = yf.Ticker(row["ticker"]).info
            mcap = info.get("marketCap", 0) or 0
            avg_vol = info.get("averageVolume", 0) or 0
            avg_price = info.get("regularMarketPrice", row["price"])
            adv_notional = avg_vol * avg_price

            if mcap >= 2_000_000_000 and adv_notional >= 100_000_000:
                row["market_cap"] = mcap
                row["adv_notional"] = adv_notional
                row["company_name"] = info.get("shortName", row["ticker"])
                filtered.append(row)
        except Exception:
            continue

    return pd.DataFrame(filtered)
```

**Performance optimization:** The `.info` call is slow (~0.5s per ticker). To avoid hammering Yahoo:
- Cache ticker metadata in a local SQLite DB (`ticker_cache.db`) with a 7-day TTL
- Only call `.info` for tickers not in cache or with expired TTL
- This turns a 50-ticker filter pass from ~25s → <2s on subsequent runs

```python
# Suggested cache schema
CREATE TABLE IF NOT EXISTS ticker_meta (
    ticker TEXT PRIMARY KEY,
    market_cap REAL,
    avg_volume REAL,
    short_name TEXT,
    exchange TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Phase 3: News Fetching

### Goal
For each filtered mover (typically 10–30 names), fetch the most relevant news article explaining the move.

### API Strategy: Dual-Source

**Source 1: Finnhub Company News**
- Endpoint: `GET /api/v1/company-news?symbol={ticker}&from={date}&to={date}`
- Free tier: 60 calls/min — plenty for 30 tickers
- Returns: headline, summary, source, URL, datetime
- Quality: Good for major wires (Reuters, Dow Jones) but can be noisy

```python
import requests
from datetime import date

def fetch_finnhub_news(ticker: str, api_key: str) -> list[dict]:
    today = date.today().isoformat()
    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": ticker,
        "from": today,
        "to": today,
        "token": api_key,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    articles = resp.json()
    # Sort by datetime descending, return top 3
    articles.sort(key=lambda x: x.get("datetime", 0), reverse=True)
    return articles[:3]
```

**Source 2: MarketAux**
- Endpoint: `GET /v1/news/all?symbols={ticker}&filter_entities=true&language=en`
- Free tier: 100 requests/day — use judiciously
- Returns: title, description, source, URL, entities, sentiment
- Quality: Better entity matching, includes sentiment scores

```python
def fetch_marketaux_news(ticker: str, api_key: str) -> list[dict]:
    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "symbols": ticker,
        "filter_entities": "true",
        "language": "en",
        "api_token": api_key,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])[:3]
```

### News Merging Strategy

```
For each ticker:
  1. Fetch from Finnhub (primary — no daily limit concerns)
  2. Fetch from MarketAux (secondary — use if Finnhub returns nothing relevant)
  3. Deduplicate by headline similarity (fuzzy match, >80% = same article)
  4. Rank by: recency × relevance (prefer articles from today, with ticker in headline)
  5. Return top 1-2 articles per ticker
```

---

## Phase 4: AI Summarization (Catalyst Extraction)

### Goal
For each mover, produce a 1-sentence "catalyst" summary: what specifically caused the move.

### Approach: Use Claude API via Anthropic SDK

```python
from anthropic import Anthropic

client = Anthropic()  # Uses ANTHROPIC_API_KEY env var

def summarize_catalyst(ticker: str, pct_change: float, headlines: list[dict]) -> str:
    """Given a ticker's move and its news articles, produce a 1-line catalyst."""
    news_text = "\n".join(
        f"- {a['headline']}: {a.get('summary', '')}" for a in headlines
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": f"""You are a prop trading desk analyst. {ticker} moved {pct_change:+.1f}% today.

Here are the news articles:
{news_text}

Write ONE sentence explaining the catalyst for the move. Be specific (name the event, number, or development). If no clear catalyst, say "No clear catalyst identified — likely technical/flow-driven."
"""
        }]
    )
    return response.content[0].text.strip()
```

### Cost Estimate
- ~30 tickers × ~300 input tokens + 50 output tokens each
- Sonnet: ~$0.01–0.03 per run. Negligible.

---

## Phase 5: Output & Display

### CLI Output (default)

Use `rich` library for a clean terminal table:

```python
from rich.console import Console
from rich.table import Table

def display_movers(movers: list[dict]):
    console = Console()
    table = Table(title="🔥 Today's Movers — Liquid Names", show_lines=True)

    table.add_column("Ticker", style="bold cyan", width=8)
    table.add_column("Name", width=20)
    table.add_column("% Chg", justify="right", width=8)
    table.add_column("Price", justify="right", width=10)
    table.add_column("Mkt Cap", justify="right", width=10)
    table.add_column("Catalyst", width=60)

    for m in movers:
        pct = m["pct_change"]
        color = "green" if pct > 0 else "red"
        table.add_row(
            m["ticker"],
            m["company_name"][:20],
            f"[{color}]{pct:+.1f}%[/{color}]",
            f"${m['price']:.2f}",
            f"${m['market_cap']/1e9:.1f}B",
            m["catalyst"],
        )

    console.print(table)
```

### Optional: TUI (Textual)

If you want a persistent dashboard that auto-refreshes, use the `textual` library:
- Live-updating table
- Press Enter on a row to expand full article text
- Hotkey to re-fetch
- This is a stretch goal — build CLI first.

### Optional: Markdown / HTML Report Export

```python
def export_markdown(movers: list[dict], filepath: str = "movers_report.md"):
    with open(filepath, "w") as f:
        f.write(f"# Daily Movers Report — {date.today()}\n\n")
        for m in movers:
            emoji = "🟢" if m["pct_change"] > 0 else "🔴"
            f.write(f"## {emoji} {m['ticker']} ({m['pct_change']:+.1f}%)\n")
            f.write(f"**{m['company_name']}** | ${m['price']:.2f} | MCap: ${m['market_cap']/1e9:.1f}B\n\n")
            f.write(f"**Catalyst:** {m['catalyst']}\n\n")
            if m.get("news_url"):
                f.write(f"[Source]({m['news_url']})\n\n")
            f.write("---\n\n")
```

---

## Project Structure

```
stock-movers/
├── README.md
├── pyproject.toml              # deps: yfinance, requests, rich, anthropic, pandas
├── .env.example                # API keys template
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point + orchestrator
│   ├── config.py               # Load .env, constants (thresholds, API URLs)
│   ├── universe.py             # Load/refresh ticker universe (S&P 500 + R1000)
│   ├── movers.py               # Phase 1: fetch prices, compute % changes
│   ├── filters.py              # Phase 2: market cap + ADV filtering
│   ├── cache.py                # SQLite ticker metadata cache
│   ├── news.py                 # Phase 3: Finnhub + MarketAux fetchers
│   ├── summarizer.py           # Phase 4: Claude API catalyst summaries
│   ├── display.py              # Phase 5: rich table output
│   └── export.py               # Optional: markdown/HTML export
├── data/
│   ├── tickers.json            # Universe file (auto-refreshed)
│   └── ticker_cache.db         # SQLite metadata cache (auto-created)
└── tests/
    ├── test_movers.py
    ├── test_filters.py
    └── test_news.py
```

---

## Build Order for Claude Code

Execute these steps in order. Each step should be committed before moving on.

### Step 1: Scaffold + Config
```
Create the project structure above. Set up pyproject.toml with dependencies:
  yfinance, pandas, requests, rich, anthropic, python-dotenv

Create config.py that loads from .env:
  FINNHUB_API_KEY, MARKETAUX_API_KEY, ANTHROPIC_API_KEY

Create .env.example with placeholder values.
```

### Step 2: Universe Management
```
Build universe.py:
  - Function to scrape S&P 500 tickers from Wikipedia
  - Function to scrape Russell 1000 tickers (or use a static list)
  - Merge, dedupe, save to data/tickers.json
  - Function to load tickers from file
  - Include a refresh check: if file is >30 days old, auto-refresh
```

### Step 3: Price Movers (Core)
```
Build movers.py:
  - get_movers(tickers, top_n=50) → DataFrame
  - Use yfinance.download with period="5d" to handle weekends
  - Compute pct_change from last 2 trading days
  - Sort by absolute pct_change
  - Handle errors gracefully (skip tickers that fail)

Write tests: test with a small ticker list (AAPL, MSFT, TSLA)
```

### Step 4: Metadata Cache + Filters
```
Build cache.py:
  - SQLite-backed cache for ticker metadata
  - get_meta(ticker) → dict or None
  - set_meta(ticker, data) → None
  - is_stale(ticker, ttl_days=7) → bool

Build filters.py:
  - apply_liquidity_filters(df) → filtered DataFrame
  - Check cache first, fall back to yfinance .info
  - Market cap >= $2B, ADV notional >= $100M
  - Cache results after fetching

Write tests for filter logic with mock data.
```

### Step 5: News Fetching
```
Build news.py:
  - fetch_finnhub_news(ticker, api_key) → list[dict]
  - fetch_marketaux_news(ticker, api_key) → list[dict]
  - get_best_news(ticker, finnhub_key, marketaux_key) → dict
    - Try Finnhub first, fall back to MarketAux
    - Return best headline + summary + URL
  - Add rate limiting (time.sleep between calls)

Write tests with mocked API responses.
```

### Step 6: AI Summarization
```
Build summarizer.py:
  - summarize_catalyst(ticker, pct_change, articles) → str
  - Use Claude claude-sonnet-4-20250514 via Anthropic SDK
  - Single sentence output
  - Handle edge case: no news found → "No catalyst identified"

Write tests with mock Claude responses.
```

### Step 7: Display + CLI
```
Build display.py:
  - display_movers(movers) using rich Table
  - Color-coded % changes (green/red)
  - Formatted market cap ($XXB)

Build main.py:
  - Orchestrate the full pipeline
  - CLI args via argparse:
    --top N       (default 20: number of movers to show)
    --min-mcap    (default 2e9: minimum market cap)
    --min-adv     (default 1e8: minimum ADV notional)
    --gainers     (show only gainers)
    --losers      (show only losers)
    --export md   (optional: export to markdown)
    --no-ai       (skip Claude summarization, just show raw headlines)
    --refresh     (force refresh ticker universe)
```

### Step 8: Polish
```
- Add proper logging (use loguru or stdlib logging)
- Add a --verbose flag
- Add error handling for API failures (retry with backoff)
- Add a --sector flag to filter by GICS sector
- Write README.md with setup instructions
- Test full pipeline end-to-end
```

---

## Environment Variables (.env)

```
FINNHUB_API_KEY=your_finnhub_key_here
MARKETAUX_API_KEY=your_marketaux_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

---

## API Rate Limits to Respect

| API        | Free Tier Limit         | Strategy                          |
|------------|-------------------------|-----------------------------------|
| yfinance   | No hard limit (unofficial) | Batch requests, add 0.5s delays |
| Finnhub    | 60 calls/min            | Process tickers sequentially      |
| MarketAux  | 100 calls/day           | Use as fallback only              |
| Claude API | Pay-per-use             | ~$0.02/run, batch prompts if needed |

---

## Example Output

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    🔥 Today's Movers — Liquid Names                         │
├──────────┬──────────────────┬─────────┬──────────┬──────────┬──────────────┤
│ Ticker   │ Name             │  % Chg  │   Price  │  Mkt Cap │ Catalyst     │
├──────────┼──────────────────┼─────────┼──────────┼──────────┼──────────────┤
│ SMCI     │ Super Micro Comp │ +18.3%  │  $42.15  │   $3.2B  │ Received     │
│          │                  │         │          │          │ compliance   │
│          │                  │         │          │          │ notice from  │
│          │                  │         │          │          │ NASDAQ...    │
├──────────┼──────────────────┼─────────┼──────────┼──────────┼──────────────┤
│ MRNA     │ Moderna Inc      │  -9.1%  │ $102.30  │  $38.5B  │ Phase 3 flu │
│          │                  │         │          │          │ combo vacc...│
├──────────┼──────────────────┼─────────┼──────────┼──────────┼──────────────┤
│ ...      │ ...              │   ...   │    ...   │    ...   │ ...          │
└──────────┴──────────────────┴─────────┴──────────┴──────────┴──────────────┘
```

---

## Stretch Goals (Post-MVP)

1. **Sector heatmap** — aggregate movers by GICS sector, show which sectors are hot/cold
2. **Historical tracking** — log each day's movers to a local DB, query patterns over time
3. **Slack/Discord webhook** — auto-post the morning movers report to a channel
4. **Earnings filter** — flag if the move is earnings-related (Finnhub has earnings calendar)
5. **Options flow** — integrate unusual options activity if you add an options data source
6. **Scheduling** — cron job or systemd timer to run at 9:45 AM and 4:15 PM ET daily
7. **Web dashboard** — FastAPI + HTMX lightweight frontend (or Streamlit for quick iteration)
