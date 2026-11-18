import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------- CORS ----------

def preflight(client, origin, request_headers=None):
    headers = {"Origin": origin, "Access-Control-Request-Method": "POST"}
    if request_headers:
        headers["Access-Control-Request-Headers"] = request_headers
    return client.options("/api/login", headers=headers)


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_preflight_allows_frontend_origin_with_credentials(client, origin):
    response = preflight(client, origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_allows_the_headers_the_frontend_sends(client):
    response = preflight(client, "http://localhost:5173", "authorization,content-type")

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:3000"])
def test_cors_preflight_rejects_other_origins(client, origin):
    response = preflight(client, origin)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


# ---------- startup ----------

@pytest.fixture
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()  # reload from the restored environment in later tests


def test_startup_fails_clearly_when_configuration_is_missing(monkeypatch, fresh_settings):
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(RuntimeError, match="^DATABASE_URL is missing"):
        with TestClient(app):  # entering runs the lifespan startup
            pass


def test_startup_succeeds_with_configuration(fresh_settings):
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
