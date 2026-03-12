import sqlite3
from datetime import datetime, timedelta

from src.config import CACHE_DB, TICKER_CACHE_TTL_DAYS

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ticker_meta (
    ticker      TEXT PRIMARY KEY,
    market_cap  REAL,
    avg_volume  REAL,
    short_name  TEXT,
    exchange    TEXT,
    sector      TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
"""

_ADD_SECTOR_COL = "ALTER TABLE ticker_meta ADD COLUMN sector TEXT"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    # Migrate existing DBs that predate the sector column
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ticker_meta)")}
    if "sector" not in cols:
        conn.execute(_ADD_SECTOR_COL)
    conn.commit()
    return conn


def get_meta(ticker: str) -> dict | None:
    """Return cached metadata dict or None if not found / stale."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM ticker_meta WHERE ticker = ?", (ticker,)
        ).fetchone()
    if row is None:
        return None
    if _is_stale(row["updated_at"]):
        return None
    return dict(row)


def set_meta(ticker: str, data: dict) -> None:
    """Insert or replace ticker metadata in the cache."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO ticker_meta (ticker, market_cap, avg_volume, short_name, exchange, sector, updated_at)
            VALUES (:ticker, :market_cap, :avg_volume, :short_name, :exchange, :sector, datetime('now'))
            ON CONFLICT(ticker) DO UPDATE SET
                market_cap  = excluded.market_cap,
                avg_volume  = excluded.avg_volume,
                short_name  = excluded.short_name,
                exchange    = excluded.exchange,
                sector      = excluded.sector,
                updated_at  = excluded.updated_at
            """,
            {
                "ticker": ticker,
                "market_cap": data.get("market_cap"),
                "avg_volume": data.get("avg_volume"),
                "short_name": data.get("short_name"),
                "exchange": data.get("exchange"),
                "sector": data.get("sector"),
            },
        )
        conn.commit()


def _is_stale(updated_at: str, ttl_days: int = TICKER_CACHE_TTL_DAYS) -> bool:
    try:
        ts = datetime.fromisoformat(updated_at)
        return datetime.now() - ts > timedelta(days=ttl_days)
    except Exception:
        return True
