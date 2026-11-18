import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")  # never overrides variables already set


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing. Please configure it in your .env file.")
    return value


DATABASE_URL = _required("DATABASE_URL")
JWT_SECRET_KEY = _required("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
