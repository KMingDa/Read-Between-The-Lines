import threading
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token
from app.infrastructure.models import Base, User
from app.main import app
from app.services import auth_service


def login(client, email="alice@example.com", password="CorrectHorse1"):
    return client.post("/api/login", json={"email": email, "password": password})


# ---------- register ----------

def test_register_returns_201_with_exact_body(register):
    response = register()

    assert response.status_code == 201
    assert response.json() == {
        "message": "Registration successful.",
        "user": {"id": 1, "email": "alice@example.com", "username": "alice"},
    }


def test_register_stores_hashed_password(register, db_session_factory):
    register()

    with db_session_factory() as db:
        assert db.query(User).one().password_hash != "CorrectHorse1"


def test_register_stores_email_lowercase_and_trims_username(register):
    response = register(email="Alice@Example.COM", username="  alice  ")

    assert response.json()["user"]["email"] == "alice@example.com"
    assert response.json()["user"]["username"] == "alice"


def test_duplicate_email_is_rejected(register):
    register()

    response = register(username="other")

    assert response.status_code == 409
    assert response.json() == {"detail": "Email is already registered."}


def test_duplicate_email_check_ignores_case(register):
    register()

    assert register(email="ALICE@example.com").status_code == 409


def test_username_of_only_spaces_padding_is_rejected(register):
    # Passes the 2-char schema check, then fails after strip().
    response = register(username=" a ")

    assert response.status_code == 422
    assert response.json() == {"detail": "Username must contain at least 2 non-space characters."}


def test_one_character_username_is_rejected(register):
    # The frontend sends the email local part as username, so "a@x.com" hits this.
    assert register(email="a@example.com", username="a").status_code == 422


def test_short_password_is_rejected(register):
    assert register(password="short").status_code == 422


def test_invalid_email_is_rejected(register):
    assert register(email="not-an-email").status_code == 422


@pytest.fixture
def file_db_app(tmp_path):
    """The app on a file-based SQLite DB, so concurrent requests get separate connections."""
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


def test_concurrent_duplicate_registrations_create_one_user(file_db_app, monkeypatch):
    both_checked = threading.Barrier(2, timeout=10)
    real_hash = auth_service.hash_password

    def hash_after_both_requests_checked_the_email(password):
        both_checked.wait()  # hashing runs between the "email taken?" check and the insert
        return real_hash(password)

    monkeypatch.setattr(auth_service, "hash_password", hash_after_both_requests_checked_the_email)
    client = TestClient(app)
    body = {"email": "race@example.com", "username": "racer", "password": "CorrectHorse1"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post("/api/register", json=body), range(2)))

    assert sorted(r.status_code for r in responses) == [201, 409]
    assert [r.json() for r in responses if r.status_code == 409] == [{"detail": "Email is already registered."}]
    with file_db_app() as db:
        assert db.query(User).count() == 1


# ---------- login ----------

def test_login_returns_token_for_that_user_with_exact_body(client, register):
    user_id = register().json()["user"]["id"]

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["access_token", "token_type", "message", "user"]
    assert body["token_type"] == "bearer"
    assert body["message"] == "Login successful."
    assert body["user"] == {"id": user_id, "email": "alice@example.com", "username": "alice"}
    assert decode_access_token(body["access_token"]) == user_id


def test_login_email_is_case_insensitive(client, register):
    register()

    assert login(client, email="ALICE@Example.com").status_code == 200


def test_wrong_password_and_unknown_email_get_same_401(client, register):
    register()

    wrong_password = login(client, password="WrongPassword1")
    unknown_email = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid email or password."}
    assert wrong_password.headers["www-authenticate"] == "Bearer"


# ---------- GET /api/me ----------

def test_me_returns_current_user(client, auth_headers):
    response = client.get("/api/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"id": 1, "email": "alice@example.com", "username": "alice"}


def test_me_returns_only_the_token_owner(client, register):
    register()
    register(email="bob@example.com", username="bob")
    bob_token = login(client, email="bob@example.com").json()["access_token"]

    response = client.get("/api/me", headers={"Authorization": f"Bearer {bob_token}"})

    assert response.json()["email"] == "bob@example.com"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic abc"}], ids=["no-header", "basic-scheme"])
def test_me_without_bearer_token_is_401(client, headers):
    response = client.get("/api/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_with_invalid_token_is_401(client):
    response = client.get("/api/me", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_for_deleted_user_is_401(client, auth_headers, db_session_factory):
    with db_session_factory() as db:
        db.query(User).delete()
        db.commit()

    response = client.get("/api/me", headers=auth_headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "User no longer exists."}


def test_me_for_token_of_user_that_never_existed_is_401(client):
    response = client.get("/api/me", headers={"Authorization": f"Bearer {create_access_token(999)}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "User no longer exists."}


def test_me_rejects_correctly_signed_token_without_expiry(client, register):
    register()  # user 1 exists, so only the missing exp can cause the rejection
    token = jwt.encode({"sub": "1"}, get_settings().jwt_secret_key, algorithm="HS256")

    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token."}
