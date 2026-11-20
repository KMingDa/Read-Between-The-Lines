import os

# Set before any `app` import. Tests never read the real .env, and the app only
# ever sees this throwaway SQLite URL and secret.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-not-used-anywhere-else-0123456789"

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.infrastructure.models import Base
from app.main import app

assert get_settings().database_url.startswith("sqlite"), "refusing to run against a real database"

BACKEND_DIR = Path(__file__).resolve().parents[1]
# The disposable test service from infra/docker-compose.yml (profile "test"), never the dev database.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://test@127.0.0.1:5433/read_between_lines_test"
)


# ---------- SQLite (default run) ----------

def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs and cascades otherwise


@pytest.fixture
def db_session_factory():
    # SQLite for speed; behaviour that differs on PostgreSQL is covered by `pytest -m postgres`.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so the request threads see the same DB
        hide_parameters=True,  # as in production, so log assertions see what production would log
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
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


# ---------- PostgreSQL (`pytest -m postgres`, disposable test service only) ----------

@pytest.fixture(scope="session")
def postgres_engine():
    url = make_url(TEST_DATABASE_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a disposable database ending in _test")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        engine.dispose()
        pytest.fail(
            "PostgreSQL test service is not reachable. Start it with: "
            "docker compose -f infra/docker-compose.yml --profile test up -d db-test"
        )
    yield engine
    engine.dispose()


@pytest.fixture
def empty_postgres(postgres_engine) -> Engine:
    """The test database with nothing in it: the public schema is dropped and recreated."""
    with postgres_engine.begin() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar().endswith("_test")
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    return postgres_engine


@pytest.fixture
def migrated_postgres(empty_postgres) -> Engine:
    """The test database built by `alembic upgrade head`, i.e. the real migrated schema."""
    with empty_postgres.begin() as connection:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return empty_postgres
