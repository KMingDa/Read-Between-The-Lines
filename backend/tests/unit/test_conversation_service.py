from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, InvalidInputError, NotFoundError, PayloadTooLargeError
from app.domain.imports import fingerprint
from app.domain.parsing import whatsapp
from app.infrastructure import conversation_repository
from app.infrastructure.models import User
from app.services import conversation_service

CHAT = (
    "10/10/2026, 21:00 - Messages and calls are end-to-end encrypted.\n"
    "10/10/2026, 21:01 - Alex: hi\n"
    "second line\n"
    "10/10/2026, 21:05 - Sam: hey\n"
)
FILENAME = "WhatsApp Chat with Alex.txt"


def add_user(db, email="alice@example.com") -> int:
    user = User(email=email, username=email.split("@")[0], password_hash="$argon2id$x")
    db.add(user)
    db.commit()
    return user.id


def import_chat(db, user_id, data=CHAT.encode(), filename=FILENAME, date_order=None):
    return conversation_service.import_whatsapp_export(
        db, user_id=user_id, filename=filename, data=data, date_order=date_order
    )


# ---------- importing ----------

def test_import_stores_the_conversation_and_returns_the_parse_report(db):
    user = add_user(db)

    result = import_chat(db, user)

    conversation = result.conversation
    assert (conversation.title, conversation.original_filename) == ("Alex", FILENAME)
    assert conversation.message_count == 3
    assert conversation.content_hash == fingerprint(CHAT)
    assert (conversation.first_message_at, conversation.last_message_at) == (
        datetime(2026, 10, 10, 21, 0), datetime(2026, 10, 10, 21, 5),
    )
    assert (result.chat.detected_date_order, result.chat.date_order_ambiguous) == ("day_first", False)
    assert result.chat.skipped_line_count == 0

    stored = conversation_repository.get_messages(db, user, conversation.id)
    assert [(m.position, m.sender, m.content) for m in stored] == [
        (0, None, "Messages and calls are end-to-end encrypted."),
        (1, "Alex", "hi\nsecond line"),
        (2, "Sam", "hey"),
    ]


def test_title_comes_from_the_senders_when_the_file_name_has_no_contact(db):
    result = import_chat(db, add_user(db), filename="_chat.txt")

    assert result.conversation.title == "Alex & Sam"


def test_the_parser_gets_the_decoded_text_not_the_fingerprint_copy(db, monkeypatch):
    received = []

    def spy(text, date_order=None):
        received.append(text)
        return whatsapp.parse_whatsapp_chat(text, date_order)

    monkeypatch.setattr(conversation_service, "parse_whatsapp_chat", spy)
    original = CHAT.replace("\n", "\r\n") + "\r\n\r\n   "

    result = import_chat(db, add_user(db), data=b"\xef\xbb\xbf" + original.encode())

    assert received == [original]  # only the BOM was removed by decoding
    assert result.conversation.content_hash == fingerprint(CHAT)


def test_date_order_override_reaches_the_parser(db):
    ambiguous = "01/02/2026, 10:00 - Alex: a\n01/03/2026, 10:00 - Sam: b\n"

    result = import_chat(db, add_user(db), data=ambiguous.encode(), date_order="month_first")

    assert result.conversation.date_order == "month_first"
    assert result.conversation.date_order_ambiguous is False
    assert result.conversation.first_message_at == datetime(2026, 1, 2, 10, 0)


def test_a_full_path_from_the_browser_is_reduced_to_the_file_name(db):
    result = import_chat(db, add_user(db), filename="C:\\fakepath\\WhatsApp Chat with Alex.txt")

    assert result.conversation.original_filename == "WhatsApp Chat with Alex.txt"


def test_a_255_character_file_name_is_accepted(db):
    name = "x" * 251 + ".txt"

    assert import_chat(db, add_user(db), filename=name).conversation.original_filename == name


@pytest.mark.parametrize(
    "filename, data, error, message",
    [
        ("chat.pdf", CHAT.encode(), InvalidInputError, ".txt"),
        ("", CHAT.encode(), InvalidInputError, "no valid file name"),
        (None, CHAT.encode(), InvalidInputError, "no valid file name"),
        ("chat\n.txt", CHAT.encode(), InvalidInputError, "no valid file name"),
        ("x" * 252 + ".txt", CHAT.encode(), InvalidInputError, "longer than 255"),
        (FILENAME, b"", InvalidInputError, "empty"),
        (FILENAME, b"\xff\xfe1\x000\x00", InvalidInputError, "not UTF-8"),  # UTF-16
        (FILENAME, b"10/10/2026, 21:01 - Alex: hi\x00", InvalidInputError, "binary"),
        (FILENAME, b"hello there", InvalidInputError, "No WhatsApp messages"),
        (FILENAME, b"10/10/2026, 21:00 - Alex left", InvalidInputError, "No WhatsApp messages"),
        (FILENAME, b"x" * (5 * 1024 * 1024 + 1), PayloadTooLargeError, "larger than 5 MB"),
    ],
    ids=["not-txt", "no-name", "none-name", "control-char", "name-too-long", "empty", "utf16",
         "nul-byte", "not-a-chat", "only-system-messages", "too-large"],
)
def test_invalid_uploads_are_rejected_and_nothing_is_stored(db, filename, data, error, message):
    user = add_user(db)

    with pytest.raises(error, match=message):
        import_chat(db, user, data=data, filename=filename)

    assert conversation_service.list_conversations(db, user) == []


# ---------- duplicates ----------

def test_the_same_file_twice_is_rejected_before_parsing(db, monkeypatch):
    user = add_user(db)
    import_chat(db, user)

    monkeypatch.setattr(conversation_service, "parse_whatsapp_chat", pytest.fail)
    with pytest.raises(ConflictError, match="already been imported"):
        import_chat(db, user, data=CHAT.replace("\n", "\r\n").encode())  # same chat, other line endings


def test_another_user_may_import_the_same_file(db):
    import_chat(db, add_user(db, "alice@example.com"))

    assert import_chat(db, add_user(db, "bob@example.com")).conversation.id is not None


def test_losing_a_race_after_the_check_is_a_conflict_and_the_session_survives(db, monkeypatch):
    user = add_user(db)
    first = import_chat(db, user).conversation.id
    real_lookup = conversation_repository.get_conversation_by_hash
    lookups = []

    def check_runs_before_the_other_commit(session, user_id, content_hash):
        lookups.append(content_hash)
        return None if len(lookups) == 1 else real_lookup(session, user_id, content_hash)

    monkeypatch.setattr(conversation_repository, "get_conversation_by_hash", check_runs_before_the_other_commit)

    with pytest.raises(ConflictError, match="already been imported"):
        import_chat(db, user)

    assert [c.id for c in conversation_service.list_conversations(db, user)] == [first]


def test_other_database_errors_are_not_reported_as_duplicates(db, monkeypatch):
    user = add_user(db)

    def failing_add(*args, **kwargs):
        raise IntegrityError("INSERT ...", {}, Exception("CHECK constraint failed"))

    monkeypatch.setattr(conversation_repository, "add_conversation", failing_add)

    with pytest.raises(IntegrityError):
        import_chat(db, user)
    assert conversation_service.list_conversations(db, user) == []


# ---------- reading and deleting ----------

def test_a_user_without_conversations_gets_an_empty_list(db):
    assert conversation_service.list_conversations(db, add_user(db)) == []


def test_detail_includes_participants_without_system_messages(db):
    user = add_user(db)
    conversation_id = import_chat(db, user).conversation.id

    overview = conversation_service.get_conversation_detail(db, user, conversation_id)

    assert overview.conversation.id == conversation_id
    assert overview.participants == [("Alex", 1), ("Sam", 1)]


def test_a_page_past_the_end_is_empty_but_not_an_error(db):
    user = add_user(db)
    conversation_id = import_chat(db, user).conversation.id

    page = conversation_service.get_message_page(db, user, conversation_id, offset=50, limit=10)

    assert (page.total, page.messages) == (3, [])


@pytest.mark.parametrize(
    "call",
    [
        lambda db, user, cid: conversation_service.get_conversation_detail(db, user, cid),
        lambda db, user, cid: conversation_service.get_message_page(db, user, cid, offset=0, limit=10),
        lambda db, user, cid: conversation_service.delete_conversation(db, user, cid),
    ],
    ids=["detail", "messages", "delete"],
)
def test_another_users_or_a_missing_conversation_is_not_found(db, call):
    alice, bob = add_user(db, "alice@example.com"), add_user(db, "bob@example.com")
    conversation_id = import_chat(db, alice).conversation.id

    for target in (conversation_id, conversation_id + 1000):
        with pytest.raises(NotFoundError, match="Conversation not found."):
            call(db, bob, target)

    assert conversation_service.get_conversation_detail(db, alice, conversation_id) is not None


def test_delete_commits(db_session_factory):
    with db_session_factory() as db:
        user = add_user(db)
        conversation_id = import_chat(db, user).conversation.id
        conversation_service.delete_conversation(db, user, conversation_id)

    with db_session_factory() as db:  # a new session sees the deletion
        assert conversation_service.list_conversations(db, user) == []
