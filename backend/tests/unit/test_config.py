import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import config

BACKEND_DIR = Path(__file__).resolve().parents[2]
VALID_SECRET = "x" * config.MIN_JWT_SECRET_LENGTH

# conftest sets PYTHON_DOTENV_DISABLED, so load_settings() never reads the real .env here,
# and monkeypatch restores every variable changed below.


@pytest.fixture
def valid_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)


def test_env_file_is_the_project_root_env():
    assert config.ENV_FILE == BACKEND_DIR.parent / ".env"


def test_settings_load_when_variables_are_set(valid_env):
    settings = config.load_settings()

    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.jwt_secret_key == VALID_SECRET


@pytest.mark.parametrize("missing", ["DATABASE_URL", "JWT_SECRET_KEY"])
def test_missing_variable_fails_clearly(monkeypatch, valid_env, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=f"^{missing} is missing"):
        config.load_settings()


@pytest.mark.parametrize("missing", ["DATABASE_URL", "JWT_SECRET_KEY"])
def test_empty_variable_counts_as_missing(monkeypatch, valid_env, missing):
    monkeypatch.setenv(missing, "")

    with pytest.raises(RuntimeError, match=f"^{missing} is missing"):
        config.load_settings()


def test_short_jwt_secret_is_rejected(monkeypatch, valid_env):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * (config.MIN_JWT_SECRET_LENGTH - 1))

    with pytest.raises(RuntimeError, match="^JWT_SECRET_KEY must be at least 32 characters"):
        config.load_settings()


def test_settings_repr_hides_secrets(monkeypatch, valid_env):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:db-password@localhost/db")

    shown = repr(config.load_settings())

    assert "db-password" not in shown
    assert VALID_SECRET not in shown


def test_get_settings_is_loaded_once():
    assert config.get_settings() is config.get_settings()


def test_importing_the_app_needs_no_configuration():
    # A fresh interpreter with no DATABASE_URL or JWT_SECRET_KEY (SYSTEMROOT is needed on Windows).
    env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "PYTHON_DOTENV_DISABLED": "1"}

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stderr
