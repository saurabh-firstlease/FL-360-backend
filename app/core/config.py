import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]

DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
MEDIA_URL = os.getenv("MEDIA_URL", f"{PUBLIC_BASE_URL}/media").rstrip("/")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

_media_root = Path(os.getenv("MEDIA_ROOT", "./media"))
MEDIA_ROOT = _media_root if _media_root.is_absolute() else (BASE_DIR / _media_root).resolve()

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "60")) * 1024 * 1024
PANO_FULL_WIDTH = int(os.getenv("PANO_FULL_WIDTH", "4096"))
PANO_PREVIEW_WIDTH = 1024

# Tests run each case in its own event loop, so pooled connections can't be reused.
DB_NULLPOOL = os.getenv("DB_NULLPOOL") == "1"
SQL_ECHO = os.getenv("SQL_ECHO") == "1"
