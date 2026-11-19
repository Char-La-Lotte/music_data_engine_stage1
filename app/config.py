import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
DB_PATH = BASE_DIR / "data" / "itv.sqlite3"
STATIC_DIR = BASE_DIR / "static"
