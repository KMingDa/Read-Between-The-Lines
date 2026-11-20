"""Alembic migrations against the disposable PostgreSQL test service (fixtures in conftest.py),
never the development database.

    docker compose -f infra/docker-compose.yml --profile test up -d db-test
    pytest -m postgres
"""

from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.infrastructure.models import Base

pytestmark = pytest.mark.postgres

BACKEND_DIR = Path(__file__).resolve().parents[2]
# The users table as create_all has built it from the User model since 714eeac, which is how the
# development database got it. Its column types, nullability and indexes were also checked
# read-only against the development database on 2026-11-18.
EXPECTED_USERS = {
    "columns": [
        ("id", "integer", None, "NO", "nextval('users_id_seq'::regclass)"),
        ("email", "character varying", 255, "NO", None),
        ("username", "character varying", 50, "NO", None),
        ("password_hash", "character varying", 255, "NO", None),
        ("created_at", "timestamp with time zone", None, "NO", "now()"),
    ],
    "constraints": [("users_pkey", "PRIMARY KEY (id)")],
    "indexes": [
        ("ix_users_email", "CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email)"),
        ("ix_users_id", "CREATE INDEX ix_users_id ON public.users USING btree (id)"),
        ("users_pkey", "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)"),
    ],
    "id_sequence": ("public.users_id_seq", "integer"),
}

EXPECTED_CONVERSATIONS = {
    "columns": [
        ("id", "integer", None, "NO", "nextval('conversations_id_seq'::regclass)"),
        ("user_id", "integer", None, "NO", None),
        ("source", "character varying", 20, "NO", "'whatsapp'::character varying"),
        ("title", "character varying", 255, "NO", None),
        ("original_filename", "character varying", 255, "NO", None),
        ("content_hash", "character varying", 64, "NO", None),
        ("message_count", "integer", None, "NO", None),
        ("first_message_at", "timestamp without time zone", None, "NO", None),
        ("last_message_at", "timestamp without time zone", None, "NO", None),
        ("date_order", "character varying", 11, "NO", None),
        ("date_order_ambiguous", "boolean", None, "NO", None),
        ("imported_at", "timestamp with time zone", None, "NO", "now()"),
    ],
    "constraints": [
        (
            "ck_conversations_date_order",
            "CHECK (((date_order)::text = ANY ((ARRAY['day_first'::character varying, "
            "'month_first'::character varying])::text[])))",
        ),
        ("conversations_pkey", "PRIMARY KEY (id)"),
        ("conversations_user_id_fkey", "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"),
        ("uq_conversations_user_id_content_hash", "UNIQUE (user_id, content_hash)"),
    ],
    "indexes": [
        ("conversations_pkey", "CREATE UNIQUE INDEX conversations_pkey ON public.conversations USING btree (id)"),
        (
            "uq_conversations_user_id_content_hash",
            "CREATE UNIQUE INDEX uq_conversations_user_id_content_hash "
            "ON public.conversations USING btree (user_id, content_hash)",
        ),
    ],
    "id_sequence": ("public.conversations_id_seq", "integer"),
}

EXPECTED_MESSAGES = {
    "columns": [
        ("id", "integer", None, "NO", "nextval('messages_id_seq'::regclass)"),
        ("conversation_id", "integer", None, "NO", None),
        ("position", "integer", None, "NO", None),
        ("sent_at", "timestamp without time zone", None, "NO", None),
        ("sender", "text", None, "YES", None),
        ("content", "text", None, "NO", None),
    ],
    "constraints": [
        (
            "messages_conversation_id_fkey",
            "FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE",
        ),
        ("messages_pkey", "PRIMARY KEY (id)"),
        ("uq_messages_conversation_id_position", 'UNIQUE (conversation_id, "position")'),
    ],
    "indexes": [
        ("messages_pkey", "CREATE UNIQUE INDEX messages_pkey ON public.messages USING btree (id)"),
        (
            "uq_messages_conversation_id_position",
            "CREATE UNIQUE INDEX uq_messages_conversation_id_position "
            'ON public.messages USING btree (conversation_id, "position")',
        ),
    ],
    "id_sequence": ("public.messages_id_seq", "integer"),
}


@pytest.fixture
def engine(empty_postgres) -> Engine:
    """The disposable test database, emptied before each test (see conftest.py)."""
    return empty_postgres


def alembic_config(connection: Connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), revision)


def snapshot(connection: Connection, table: str) -> dict:
    """Columns, constraints, indexes and id sequence of a table, read from the Postgres catalog."""
    params = {"table": table}
    columns = connection.execute(text(
        "SELECT column_name, data_type, character_maximum_length, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table "
        "ORDER BY ordinal_position"
    ), params).all()
    constraints = connection.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = to_regclass('public.' || :table) ORDER BY conname"
    ), params).all()
    indexes = connection.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'public' AND tablename = :table ORDER BY indexname"
    ), params).all()
    sequence = connection.execute(text(
        "SELECT s.schemaname || '.' || s.sequencename, s.data_type::text FROM pg_sequences s "
        "WHERE s.schemaname || '.' || s.sequencename = pg_get_serial_sequence('public.' || :table, 'id')"
    ), params).one()
    return {
        "columns": [tuple(row) for row in columns],
        "constraints": [tuple(row) for row in constraints],
        "indexes": [tuple(row) for row in indexes],
        "id_sequence": tuple(sequence),
    }


def table_names(connection: Connection) -> set[str]:
    return set(connection.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )).scalars())


def add_user(connection: Connection, email: str = "a@example.com") -> int:
    return connection.execute(text(
        "INSERT INTO users (email, username, password_hash) VALUES (:email, 'user', '$argon2id$x') "
        "RETURNING id"
    ), {"email": email}).scalar()


def add_conversation(connection: Connection, user_id: int, content_hash: str = "h" * 64) -> int:
    return connection.execute(text(
        "INSERT INTO conversations (user_id, title, original_filename, content_hash, message_count, "
        "first_message_at, last_message_at, date_order, date_order_ambiguous) VALUES (:user_id, "
        "'Chat', 'chat.txt', :hash, 1, '2026-10-10 09:00', '2026-10-10 09:00', 'day_first', false) "
        "RETURNING id"
    ), {"user_id": user_id, "hash": content_hash}).scalar()


def add_message(connection: Connection, conversation_id: int, position: int, sent_at="2026-10-10 09:00"):
    connection.execute(text(
        "INSERT INTO messages (conversation_id, position, sent_at, sender, content) "
        "VALUES (:conversation_id, :position, :sent_at, 'Alex', 'hi')"
    ), {"conversation_id": conversation_id, "position": position, "sent_at": sent_at})


# ---------- users baseline ----------

def test_baseline_creates_users_exactly_like_the_existing_table(engine):
    upgrade(engine, "0001")

    with engine.connect() as connection:
        assert snapshot(connection, "users") == EXPECTED_USERS


def test_expected_users_schema_is_what_create_all_built(engine):
    # Rebuild the table the way init_db.py built the development database.
    with engine.begin() as connection:
        Base.metadata.tables["users"].create(connection)

    with engine.connect() as connection:
        assert snapshot(connection, "users") == EXPECTED_USERS


def test_existing_users_survive_stamp_and_upgrade(engine):
    # The development database's situation: a create_all users table holding real rows.
    with engine.begin() as connection:
        Base.metadata.tables["users"].create(connection)
        add_user(connection, "a@example.com")
        add_user(connection, "b@example.com")
        before = connection.execute(text("SELECT * FROM users ORDER BY id")).all()

    with engine.begin() as connection:
        command.stamp(alembic_config(connection), "0001")
    upgrade(engine)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT * FROM users ORDER BY id")).all() == before
        assert add_user(connection, "c@example.com") == 3  # the id sequence carries on
        assert snapshot(connection, "users") == EXPECTED_USERS
        command.check(alembic_config(connection))


def test_baseline_downgrade_refuses_and_rolls_back(engine):
    upgrade(engine)
    with engine.begin() as connection:
        add_user(connection)

    with pytest.raises(RuntimeError, match="Refusing to drop the users table"):
        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "base")

    with engine.connect() as connection:
        assert table_names(connection) == {"alembic_version", "users", "conversations", "messages"}
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 1
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"


# ---------- full chain ----------

def test_upgrade_from_empty_database_matches_the_models(engine):
    upgrade(engine)

    with engine.begin() as connection:
        assert table_names(connection) == {"alembic_version", "users", "conversations", "messages"}
        command.check(alembic_config(connection))  # raises if migrations and models differ


def test_conversation_tables_match_the_design(engine):
    upgrade(engine)

    with engine.connect() as connection:
        assert snapshot(connection, "conversations") == EXPECTED_CONVERSATIONS
        assert snapshot(connection, "messages") == EXPECTED_MESSAGES


def test_downgrade_to_baseline_removes_only_the_new_tables(engine):
    upgrade(engine)
    with engine.begin() as connection:
        add_user(connection)

    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0001")

    with engine.connect() as connection:
        assert table_names(connection) == {"alembic_version", "users"}
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 1
    upgrade(engine)  # and the upgrade can be repeated
    with engine.connect() as connection:
        assert table_names(connection) == {"alembic_version", "users", "conversations", "messages"}


# ---------- constraints on the new tables ----------

def test_deleting_cascades_from_user_to_conversations_to_messages(engine):
    upgrade(engine)
    with engine.begin() as connection:
        user = add_user(connection)
        kept = add_conversation(connection, user, "a" * 64)
        deleted = add_conversation(connection, user, "b" * 64)
        add_message(connection, kept, 0)
        add_message(connection, deleted, 0)
        add_message(connection, deleted, 1)

        connection.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": deleted})
        assert connection.execute(text("SELECT conversation_id FROM messages")).scalars().all() == [kept]

        connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": user})
        assert connection.execute(text("SELECT count(*) FROM conversations")).scalar() == 0
        assert connection.execute(text("SELECT count(*) FROM messages")).scalar() == 0


def test_same_export_twice_is_rejected_per_user_only(engine):
    upgrade(engine)
    with engine.begin() as connection:
        alice, bob = add_user(connection, "a@example.com"), add_user(connection, "b@example.com")
        add_conversation(connection, alice)
        add_conversation(connection, bob)  # another user may import the same file

    with pytest.raises(IntegrityError, match="uq_conversations_user_id_content_hash"):
        with engine.begin() as connection:
            add_conversation(connection, alice)


def test_message_positions_are_unique_within_a_conversation(engine):
    upgrade(engine)
    with engine.begin() as connection:
        conversation = add_conversation(connection, add_user(connection))
        add_message(connection, conversation, 0)

    with pytest.raises(IntegrityError, match="uq_messages_conversation_id_position"):
        with engine.begin() as connection:
            add_message(connection, conversation, 0)


@pytest.mark.parametrize("session_time_zone", ["UTC", "Europe/Berlin", "America/New_York", "Asia/Kolkata"])
def test_message_times_are_stored_exactly_as_written(engine, session_time_zone):
    # 02:30 on 29 March 2026 does not exist in Berlin (clocks jump to 03:00); it must still
    # come back unchanged, whatever time zone the database session uses.
    exported = datetime(2026, 3, 29, 2, 30)
    upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text(f"SET TIME ZONE '{session_time_zone}'"))
        conversation = add_conversation(connection, add_user(connection))
        add_message(connection, conversation, 0, sent_at=exported)

        stored = connection.execute(text("SELECT sent_at FROM messages")).scalar()

    assert stored == exported
    assert stored.tzinfo is None
