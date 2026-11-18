"""The app's engine keeps bound SQL parameters (emails, usernames, password hashes)
out of SQLAlchemy error text and SQL logs, so server logs cannot leak them."""

import logging

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.database import get_engine
from app.infrastructure.models import Base, User

EMAIL = "private-param@example.com"
USERNAME = "private-username-param"
PASSWORD_HASH = "$argon2id$v=19$private-hash-param"


@pytest.fixture
def app_engine():
    # The production factory and options, without touching the engine cached by get_engine().
    engine = get_engine.__wrapped__()
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def insert_duplicate_user(engine) -> IntegrityError:
    with Session(engine) as db:
        db.add(User(email=EMAIL, username="first", password_hash=PASSWORD_HASH))
        db.commit()
        db.add(User(email=EMAIL, username=USERNAME, password_hash=PASSWORD_HASH))
        with pytest.raises(IntegrityError) as error:
            db.commit()
    return error.value


def test_database_error_text_does_not_show_sql_parameters(app_engine):
    error = insert_duplicate_user(app_engine)

    shown = f"{error}\n{error!r}"
    assert "INSERT INTO users" in shown  # the statement itself is still there for debugging
    for secret in (EMAIL, USERNAME, PASSWORD_HASH):
        assert secret not in shown


def test_sql_logging_does_not_show_sql_parameters(app_engine, caplog):
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")

    insert_duplicate_user(app_engine)

    assert "INSERT INTO users" in caplog.text  # SQL logging really was on
    for secret in (EMAIL, USERNAME, PASSWORD_HASH):
        assert secret not in caplog.text
