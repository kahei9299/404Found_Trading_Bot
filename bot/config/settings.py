import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RST_API_KEY", "").strip()
SECRET_KEY = os.getenv("RST_SECRET_KEY", "").strip()
BASE_URL = "https://mock-api.roostoo.com"

MARKET_DATA_PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "binance").strip().lower()
MARKET_DATA_BASE_URL = os.getenv("MARKET_DATA_BASE_URL", "https://api.binance.com").strip().rstrip("/")
MARKET_DATA_DEFAULT_QUOTE = os.getenv("MARKET_DATA_DEFAULT_QUOTE", "USDT").strip().upper()

BOT_MODE = os.getenv("BOT_MODE", "paper").strip().lower()
BOT_DB_PATH = os.getenv("BOT_DB_PATH", "bot_state.sqlite3").strip()
BOT_POLL_SECONDS = int(os.getenv("BOT_POLL_SECONDS", "60").strip())
BOT_PAIRS = tuple(pair.strip() for pair in os.getenv("BOT_PAIRS", "BTC/USD").split(",") if pair.strip())
BOT_INTERVAL = os.getenv("BOT_INTERVAL", "1h").strip()
BOT_CANDLE_LIMIT = int(os.getenv("BOT_CANDLE_LIMIT", "250").strip())
BOT_MAX_TRADE_NOTIONAL = float(os.getenv("BOT_MAX_TRADE_NOTIONAL", "1000").strip())
BOT_MAX_DAILY_LOSS = float(os.getenv("BOT_MAX_DAILY_LOSS", "250").strip())
BOT_MAX_OPEN_POSITIONS = int(os.getenv("BOT_MAX_OPEN_POSITIONS", "3").strip())
BOT_MIN_BALANCE = float(os.getenv("BOT_MIN_BALANCE", "100").strip())
