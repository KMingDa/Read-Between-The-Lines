import os

# Must run before any `app` import: load_dotenv() never overrides variables that
# are already set, so the app never sees the development DATABASE_URL or secret.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-not-used-anywhere-else-0123456789"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, engine as app_engine
from app.main import app, get_db
from app import models  # noqa: F401  (registers the User table on Base.metadata)

assert app_engine.url.drivername.startswith("sqlite"), "refusing to run against a real database"


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
def client(db_session_factory):
    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

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
