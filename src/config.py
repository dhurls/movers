import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")

# Liquidity filter thresholds
MIN_MARKET_CAP = 2_000_000_000       # $2B
MIN_ADV_NOTIONAL = 100_000_000       # $100M average daily volume (notional)

# Pipeline defaults
DEFAULT_TOP_N = 20                   # movers to display
DEFAULT_CANDIDATES = 200             # raw movers to evaluate before filtering
TICKER_CACHE_TTL_DAYS = 7
UNIVERSE_REFRESH_DAYS = 30

# Data paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TICKERS_FILE = os.path.join(DATA_DIR, "tickers.json")
CACHE_DB = os.path.join(DATA_DIR, "ticker_cache.db")

# API URLs
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
MARKETAUX_BASE_URL = "https://api.marketaux.com/v1"
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"
