import importlib.util
from pathlib import Path

import dotenv
import pytest

CONFIG_PATH = Path(__file__).resolve().parents[1] / "app" / "core" / "config.py"


# ---------- CORS ----------

def preflight(client, origin):
    return client.options(
        "/api/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


def test_cors_preflight_allows_frontend_origin_with_credentials(client):
    response = preflight(client, "http://localhost:5173")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_rejects_unrelated_origin(client):
    response = preflight(client, "http://evil.example")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


# ---------- config loading ----------

def load_fresh_config():
    # Separate module name: the real app.core.config in sys.modules stays untouched.
    spec = importlib.util.spec_from_file_location("config_under_test", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_dotenv(monkeypatch):
    # Without this, config.py would refill the deleted variable from the real .env.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)


@pytest.mark.parametrize("missing", ["DATABASE_URL", "JWT_SECRET_KEY"])
def test_config_fails_clearly_when_required_variable_is_missing(monkeypatch, no_dotenv, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=f"^{missing} is missing"):
        load_fresh_config()


@pytest.mark.parametrize("missing", ["DATABASE_URL", "JWT_SECRET_KEY"])
def test_config_treats_empty_variable_as_missing(monkeypatch, no_dotenv, missing):
    monkeypatch.setenv(missing, "")

    with pytest.raises(RuntimeError, match=f"^{missing} is missing"):
        load_fresh_config()


def test_config_loads_when_variables_are_set(monkeypatch, no_dotenv):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET_KEY", "another-test-secret")

    config = load_fresh_config()

    assert config.DATABASE_URL == "sqlite+pysqlite:///:memory:"
    assert config.JWT_SECRET_KEY == "another-test-secret"
