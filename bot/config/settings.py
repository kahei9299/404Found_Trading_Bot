import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RST_API_KEY", "").strip()
SECRET_KEY = os.getenv("RST_SECRET_KEY", "").strip()
BASE_URL = "https://mock-api.roostoo.com"

MARKET_DATA_PROVIDER = os.getenv("MARKET_DATA_PROVIDER", "binance").strip().lower()
MARKET_DATA_BASE_URL = os.getenv("MARKET_DATA_BASE_URL", "https://api.binance.com").strip().rstrip("/")
MARKET_DATA_DEFAULT_QUOTE = os.getenv("MARKET_DATA_DEFAULT_QUOTE", "USDT").strip().upper()
