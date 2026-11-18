import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AuthenticationError, ConflictError, InvalidInputError
from app.core.security import create_access_token, hash_password, verify_password
from app.infrastructure import user_repository
from app.infrastructure.models import User
from app.services import auth_service


def register(db, email="alice@example.com", username="alice", password="CorrectHorse1"):
    return auth_service.register_user(db, email, username, password)


# ---------- registration ----------

def test_register_stores_user_with_hashed_password(db):
    user = register(db)

    stored = db.get(User, user.id)
    assert (stored.email, stored.username) == ("alice@example.com", "alice")
    assert stored.password_hash != "CorrectHorse1"
    assert verify_password("CorrectHorse1", stored.password_hash)


@pytest.mark.parametrize(
    "raw, normalized",
    [
        ("Alice@Example.COM", "alice@example.com"),
        ("  bob@example.com  ", "bob@example.com"),
        ("CAROL@EXAMPLE.COM", "carol@example.com"),
    ],
)
def test_register_normalizes_email(db, raw, normalized):
    assert register(db, email=raw).email == normalized


def test_register_trims_username(db):
    assert register(db, username="  alice  ").username == "alice"


@pytest.mark.parametrize("username", ["", " ", " a ", "a"])
def test_register_rejects_username_shorter_than_two_characters(db, username):
    with pytest.raises(InvalidInputError, match="at least 2 non-space characters"):
        register(db, username=username)

    assert db.query(User).count() == 0


@pytest.mark.parametrize("email", ["alice@example.com", "ALICE@example.com", " Alice@Example.com "])
def test_register_rejects_duplicate_email_in_any_case(db, email):
    register(db)

    with pytest.raises(ConflictError, match="^Email is already registered.$"):
        register(db, email=email, username="other")

    assert db.query(User).count() == 1


def test_register_handles_losing_a_race_to_a_concurrent_registration(db, monkeypatch):
    # The other request commits between our "email taken?" check and our insert:
    # our check sees nothing, then the unique constraint rejects the insert.
    register(db)
    real_lookup = user_repository.get_user_by_email
    lookups = []

    def check_runs_before_the_other_commit(session, email):
        lookups.append(email)
        return None if len(lookups) == 1 else real_lookup(session, email)

    monkeypatch.setattr(user_repository, "get_user_by_email", check_runs_before_the_other_commit)

    with pytest.raises(ConflictError, match="^Email is already registered.$"):
        register(db, email="Alice@example.com", username="alice2")

    assert db.query(User).count() == 1  # session was rolled back and is still usable


def test_register_does_not_hide_other_database_errors(db, monkeypatch):
    def failing_commit():
        raise IntegrityError("INSERT ...", {}, Exception("NOT NULL constraint failed"))

    monkeypatch.setattr(db, "commit", failing_commit)

    with pytest.raises(IntegrityError):
        register(db)


# ---------- login ----------

def test_authenticate_returns_user_for_valid_credentials(db):
    user = register(db)

    assert auth_service.authenticate_user(db, "alice@example.com", "CorrectHorse1").id == user.id


def test_authenticate_ignores_email_case_and_spaces(db):
    register(db)

    assert auth_service.authenticate_user(db, " ALICE@Example.com ", "CorrectHorse1").email == "alice@example.com"


def test_authenticate_finds_emails_stored_with_capitals(db):
    # Rows created outside the app may not be lower-case.
    db.add(User(email="Legacy@Example.com", username="legacy", password_hash=hash_password("pw-legacy-1")))
    db.commit()

    assert auth_service.authenticate_user(db, "legacy@example.com", "pw-legacy-1").username == "legacy"


@pytest.mark.parametrize(
    "email, password",
    [("alice@example.com", "WrongHorse1"), ("nobody@example.com", "CorrectHorse1")],
    ids=["wrong-password", "unknown-email"],
)
def test_authenticate_rejects_bad_credentials_with_one_message(db, email, password):
    register(db)

    with pytest.raises(AuthenticationError, match="^Invalid email or password.$"):
        auth_service.authenticate_user(db, email, password)


# ---------- token -> user ----------

def test_token_resolves_to_its_user(db):
    user = register(db)

    assert auth_service.get_user_for_token(db, create_access_token(user.id)).id == user.id


def test_valid_token_of_deleted_user_is_rejected(db):
    user = register(db)
    token = create_access_token(user.id)
    db.delete(user)
    db.commit()

    with pytest.raises(AuthenticationError, match="^User no longer exists.$"):
        auth_service.get_user_for_token(db, token)


def test_valid_token_for_id_that_never_existed_is_rejected(db):
    with pytest.raises(AuthenticationError, match="^User no longer exists.$"):
        auth_service.get_user_for_token(db, create_access_token(999))


def test_invalid_token_is_rejected_before_any_lookup(db):
    with pytest.raises(AuthenticationError, match="^Invalid or expired token.$"):
        auth_service.get_user_for_token(db, "garbage")
