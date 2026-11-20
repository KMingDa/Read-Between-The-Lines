"""Conversation repository on SQLite (default run) and on the migrated PostgreSQL test database
(`pytest -m postgres`). Every test runs on both."""

import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.entities import Message, ParsedChat
from app.infrastructure import conversation_repository as repo
from app.infrastructure.models import Conversation, ConversationMessage, User

HASH_A = "a" * 64
HASH_B = "b" * 64


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def session_factory(request):
    if request.param == "sqlite":
        return request.getfixturevalue("db_session_factory")
    return sessionmaker(bind=request.getfixturevalue("migrated_postgres"), autoflush=False)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 25, hour, minute)


def add_user(db, email: str = "alice@example.com") -> int:
    user = User(email=email, username=email.split("@")[0], password_hash="$argon2id$x")
    db.add(user)
    db.flush()
    return user.id


def add(db, user_id: int, messages=None, *, content_hash=HASH_A, date_order="day_first", ambiguous=False):
    messages = messages or [Message(at(9), "Alex", "hi"), Message(at(9, 5), "Sam", "hey")]
    chat = ParsedChat(
        messages=tuple(messages),
        detected_date_order=date_order,
        date_order_ambiguous=ambiguous,
        skipped_line_count=0,
        warnings=(),
    )
    return repo.add_conversation(
        db, user_id=user_id, title="Alex & Sam", original_filename="chat.txt",
        content_hash=content_hash, chat=chat,
    )


def count(db, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions))


# ---------- adding ----------

def test_stores_conversation_metadata(session_factory):
    with session_factory() as db:
        user = add_user(db)
        conversation_id = add(db, user, [
            Message(at(9), "Alex", "hi"),
            Message(at(9, 1), None, "Messages and calls are end-to-end encrypted."),
            Message(at(9, 7), "Sam", "hey"),
        ], ambiguous=True).id
        db.commit()

    with session_factory() as db:  # a fresh session reads back what the database stored
        stored = repo.get_conversation(db, user, conversation_id)
        assert (stored.title, stored.original_filename, stored.content_hash, stored.source) == (
            "Alex & Sam", "chat.txt", HASH_A, "whatsapp",
        )
        assert stored.message_count == 3  # the system message counts too
        assert (stored.first_message_at, stored.last_message_at) == (at(9), at(9, 7))
        assert (stored.date_order, stored.date_order_ambiguous) == ("day_first", True)
        assert stored.imported_at is not None


def test_stores_messages_exactly_as_parsed(session_factory):
    exported = [
        Message(at(9), "Alex", "line one\nline two"),
        Message(at(9, 1), None, "Sam joined"),
        Message(at(9, 2), "Zoë 🌸", "emoji ✓ and ünïcode"),
        Message(at(9, 3), "S" * 300, "a sender name longer than 255 characters"),
    ]
    with session_factory() as db:
        user = add_user(db)
        conversation_id = add(db, user, exported).id
        db.commit()

    with session_factory() as db:
        stored = repo.get_messages(db, user, conversation_id)
        assert [(m.position, m.sent_at, m.sender, m.content) for m in stored] == [
            (0, at(9), "Alex", "line one\nline two"),
            (1, at(9, 1), None, "Sam joined"),
            (2, at(9, 2), "Zoë 🌸", "emoji ✓ and ünïcode"),
            (3, at(9, 3), "S" * 300, "a sender name longer than 255 characters"),
        ]
        assert all(message.sent_at.tzinfo is None for message in stored)


def test_export_order_is_kept_when_times_repeat_or_go_back(session_factory):
    exported = [
        Message(at(2, 50), "Alex", "before the clocks went back"),
        Message(at(2, 5), "Sam", "after the clocks went back"),  # earlier clock time, later message
        Message(at(2, 5), "Alex", "same minute, first"),
        Message(at(2, 5), "Sam", "same minute, second"),
    ]
    with session_factory() as db:
        user = add_user(db)
        conversation_id = add(db, user, exported).id
        db.commit()

    with session_factory() as db:
        stored = repo.get_messages(db, user, conversation_id)
        assert [(m.position, m.content) for m in stored] == [
            (0, "before the clocks went back"),
            (1, "after the clocks went back"),
            (2, "same minute, first"),
            (3, "same minute, second"),
        ]
        conversation = repo.get_conversation(db, user, conversation_id)
        # first/last are the earliest and latest times, not the first and last lines
        assert (conversation.first_message_at, conversation.last_message_at) == (at(2, 5), at(2, 50))


def test_a_chat_without_messages_is_rejected(session_factory):
    with session_factory() as db:
        user = add_user(db)
        with pytest.raises(ValueError, match="at least one message"):
            repo.add_conversation(
                db, user_id=user, title="t", original_filename="f.txt", content_hash=HASH_A,
                chat=ParsedChat(messages=(), detected_date_order="day_first",
                                date_order_ambiguous=False, skipped_line_count=0, warnings=()),
            )
        db.commit()
        assert count(db, Conversation) == 0


def test_unknown_date_order_is_rejected_by_the_database(session_factory):
    with session_factory() as db:
        user = add_user(db)
        with pytest.raises(IntegrityError, match="ck_conversations_date_order|CHECK constraint"):
            add(db, user, date_order="dmy")


def test_the_database_rejects_the_same_export_twice_for_one_user(session_factory):
    with session_factory() as db:
        alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
        first = add(db, alice).id
        add(db, bob)  # another user may import the same file
        db.commit()

        with pytest.raises(IntegrityError, match="uq_conversations_user_id_content_hash|UNIQUE constraint"):
            add(db, alice, [Message(at(10), "Alex", "other messages, same hash")])
        db.rollback()  # the caller owns the transaction and rolls back

        assert [c.id for c in repo.list_conversations(db, alice)] == [first]
        assert count(db, ConversationMessage) == 4  # 2 + 2; nothing from the failed attempt


def test_nothing_is_committed_by_the_repository(session_factory):
    with session_factory() as db:
        user = add_user(db)
        db.commit()
        add(db, user)
        db.rollback()

        assert repo.list_conversations(db, user) == []
        assert count(db, ConversationMessage) == 0


def test_messages_are_inserted_in_bulk_not_one_by_one(session_factory):
    exported = [Message(at(9) + timedelta(seconds=i), "Alex", f"m{i}") for i in range(2500)]
    insert_statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO MESSAGES"):
            insert_statements.append(statement)

    with session_factory() as db:
        user = add_user(db)
        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            add(db, user, exported)
            db.commit()
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert count(db, ConversationMessage) == 2500
    assert 1 <= len(insert_statements) <= 25  # a few batched statements, not 2,500


# ---------- reading ----------

def test_get_conversation_by_hash_is_scoped_to_its_owner(session_factory):
    with session_factory() as db:
        alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
        conversation_id = add(db, alice).id
        db.commit()

        assert repo.get_conversation_by_hash(db, alice, HASH_A).id == conversation_id
        assert repo.get_conversation_by_hash(db, bob, HASH_A) is None
        assert repo.get_conversation_by_hash(db, alice, HASH_B) is None


def test_lists_only_the_users_conversations_newest_first(session_factory):
    with session_factory() as db:
        alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
        db.commit()
        older = add(db, alice, content_hash=HASH_A).id
        db.commit()
        newer = add(db, alice, content_hash=HASH_B).id
        db.commit()
        add(db, bob, content_hash=HASH_A)
        db.commit()

        assert [c.id for c in repo.list_conversations(db, alice)] == [newer, older]
        assert repo.list_conversations(db, add_user(db, "carol@example.com")) == []


def test_pages_through_messages_in_position_order(session_factory):
    exported = [Message(at(9, i), "Alex", f"m{i}") for i in range(5)]
    with session_factory() as db:
        user = add_user(db)
        conversation_id = add(db, user, exported).id
        db.commit()

        def page(offset, limit):
            return [m.position for m in repo.get_messages(db, user, conversation_id, offset=offset, limit=limit)]

        assert page(0, 2) == [0, 1]
        assert page(2, 2) == [2, 3]
        assert page(4, 2) == [4]
        assert page(5, 2) == []
        assert page(0, 200) == [0, 1, 2, 3, 4]


def test_counts_messages_per_participant_without_system_messages(session_factory):
    senders = ["Alex", "Sam", None, "Alex", "Bea", "Sam", "Alex", "Bea"]
    with session_factory() as db:
        user = add_user(db)
        conversation_id = add(db, user, [
            Message(at(9, i), sender, f"m{i}") for i, sender in enumerate(senders)
        ]).id
        db.commit()

        assert repo.get_participants(db, user, conversation_id) == [("Alex", 3), ("Bea", 2), ("Sam", 2)]


def test_another_users_conversation_looks_exactly_like_a_missing_one(session_factory):
    with session_factory() as db:
        alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
        conversation_id = add(db, alice).id
        db.commit()

        for target in (conversation_id, conversation_id + 1000):  # Alice's, and one that does not exist
            assert repo.get_conversation(db, bob, target) is None
            assert repo.get_messages(db, bob, target) == []
            assert repo.get_participants(db, bob, target) == []
            assert repo.delete_conversation(db, bob, target) is False
        db.commit()

        assert repo.get_conversation(db, alice, conversation_id) is not None
        assert len(repo.get_messages(db, alice, conversation_id)) == 2


# ---------- deleting ----------

def test_deleting_a_conversation_removes_its_messages(session_factory):
    with session_factory() as db:
        user = add_user(db)
        kept = add(db, user, content_hash=HASH_A).id
        deleted = add(db, user, content_hash=HASH_B).id
        db.commit()

        assert repo.delete_conversation(db, user, deleted) is True
        db.commit()

        assert repo.get_conversation(db, user, deleted) is None
        assert count(db, ConversationMessage, ConversationMessage.conversation_id == deleted) == 0
        assert len(repo.get_messages(db, user, kept)) == 2
        assert repo.delete_conversation(db, user, deleted) is False  # already gone


def test_deleting_a_user_removes_their_conversations_and_messages(session_factory):
    with session_factory() as db:
        alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
        add(db, alice)
        bobs = add(db, bob).id
        db.commit()

        db.execute(delete(User).where(User.id == alice))
        db.commit()

        assert count(db, Conversation) == 1
        assert count(db, ConversationMessage) == 2
        assert repo.get_conversation(db, bob, bobs) is not None


# ---------- scale (PostgreSQL only) ----------

@pytest.mark.postgres
def test_imports_100000_messages(migrated_postgres):
    session_factory = sessionmaker(bind=migrated_postgres, autoflush=False)
    exported = [
        Message(datetime(2026, 1, 1) + timedelta(seconds=i),
                None if i % 1000 == 0 else ("Alex" if i % 2 else "Sam"), f"message {i}")
        for i in range(100_000)
    ]

    started = time.perf_counter()
    with session_factory() as db:
        user = add_user(db)
        conversation_id = add(db, user, exported).id
        db.commit()
    elapsed = time.perf_counter() - started

    with session_factory() as db:
        assert repo.get_conversation(db, user, conversation_id).message_count == 100_000
        assert count(db, ConversationMessage) == 100_000
        last_page = repo.get_messages(db, user, conversation_id, offset=99_998, limit=5)
        assert [(m.position, m.content) for m in last_page] == [(99_998, "message 99998"), (99_999, "message 99999")]

        assert repo.delete_conversation(db, user, conversation_id) is True
        db.commit()
        assert count(db, ConversationMessage) == 0
    print(f"\n100,000 messages inserted and committed in {elapsed:.1f}s")  # informational, no time limit
