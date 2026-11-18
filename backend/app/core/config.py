"""Application settings, read from the environment and the project-root .env file."""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
MIN_JWT_SECRET_LENGTH = 32  # 256 bits, the HS256 key size
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)  # contains the database password
    jwt_secret_key: str = field(repr=False)


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is missing. Please configure it in your .env file.")
    return value


def load_settings() -> Settings:
    """Read settings, first filling missing variables from .env (variables already set win)."""
    load_dotenv(ENV_FILE)
    jwt_secret_key = _required("JWT_SECRET_KEY")
    if len(jwt_secret_key) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters long."
        )
    return Settings(database_url=_required("DATABASE_URL"), jwt_secret_key=jwt_secret_key)


@lru_cache
def get_settings() -> Settings:
    """Settings for this process, loaded on first use rather than at import time."""
    return load_settings()
