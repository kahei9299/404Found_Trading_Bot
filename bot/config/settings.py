import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RST_API_KEY", "").strip()
SECRET_KEY = os.getenv("RST_SECRET_KEY", "").strip()
BASE_URL = "https://mock-api.roostoo.com"
