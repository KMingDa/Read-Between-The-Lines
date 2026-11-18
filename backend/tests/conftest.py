import os

# Set before any `app` import. Tests never read the real .env, and the app only
# ever sees this throwaway SQLite URL and secret.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-not-used-anywhere-else-0123456789"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.infrastructure.models import Base
from app.main import app

assert get_settings().database_url.startswith("sqlite"), "refusing to run against a real database"


@pytest.fixture
def db_session_factory():
    # shortcut: SQLite, not Postgres; Postgres-only behaviour is not covered, add a Postgres test DB in Step 5.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so the request threads see the same DB
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


@pytest.fixture
def db(db_session_factory):
    with db_session_factory() as session:
        yield session


@pytest.fixture
def client(db_session_factory):
    def override_get_db():
        with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def register(client):
    def _register(email="alice@example.com", username="alice", password="CorrectHorse1"):
        return client.post(
            "/api/register",
            json={"email": email, "username": username, "password": password},
        )

    return _register


@pytest.fixture
def auth_headers(client, register):
    register()
    response = client.post(
        "/api/login",
        json={"email": "alice@example.com", "password": "CorrectHorse1"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
