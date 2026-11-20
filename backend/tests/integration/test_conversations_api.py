"""Chat import and conversation endpoints, through FastAPI with real multipart uploads."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.domain.parsing import whatsapp
from app.infrastructure import conversation_repository
from app.infrastructure.models import Base, ConversationMessage
from app.main import app
from app.services import conversation_service

MB5 = 5 * 1024 * 1024
FILENAME = "WhatsApp Chat with Alex.txt"
CHAT = (
    "10/10/2026, 21:00 - Messages and calls are end-to-end encrypted.\n"
    "10/10/2026, 21:01 - Alex: hi\n"
    "second line\n"
    "10/10/2026, 21:05 - Sam: hey\n"
)


def login(client, email="alice@example.com"):
    client.post("/api/register", json={"email": email, "username": email.split("@")[0], "password": "CorrectHorse1"})
    token = client.post("/api/login", json={"email": email, "password": "CorrectHorse1"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, data=CHAT.encode(), filename=FILENAME, date_order=None, content_type="text/plain"):
    return client.post(
        "/api/conversations/import",
        files={"file": (filename, data, content_type)},
        data={"date_order": date_order} if date_order else None,
        headers=headers,
    )


@pytest.fixture
def alice(client):
    return login(client, "alice@example.com")


@pytest.fixture
def bob(client):
    return login(client, "bob@example.com")


# ---------- import ----------

def test_import_returns_201_with_the_conversation_and_the_parse_report(client, alice):
    response = upload(client, alice)

    assert response.status_code == 201
    body = response.json()
    assert list(body) == ["conversation", "detected_date_order", "date_order_ambiguous", "skipped_line_count", "warnings"]
    assert (body["detected_date_order"], body["date_order_ambiguous"], body["skipped_line_count"], body["warnings"]) == (
        "day_first", False, 0, [],
    )
    conversation = body["conversation"]
    assert set(conversation) == {
        "id", "title", "source", "original_filename", "message_count", "first_message_at",
        "last_message_at", "date_order", "date_order_ambiguous", "imported_at",
    }
    assert (conversation["title"], conversation["original_filename"], conversation["source"]) == ("Alex", FILENAME, "whatsapp")
    assert conversation["message_count"] == 3
    assert (conversation["first_message_at"], conversation["last_message_at"]) == ("2026-10-10T21:00:00", "2026-10-10T21:05:00")


def test_parser_warnings_and_skipped_lines_are_returned(client, alice):
    response = upload(client, alice, data=b"junk before\n01/02/2026, 10:00 - Alex: a\n01/03/2026, 10:00 - Sam: b\n")

    body = response.json()
    assert (body["skipped_line_count"], body["date_order_ambiguous"]) == (1, True)
    assert len(body["warnings"]) == 1 and "ambiguous" in body["warnings"][0]


def test_date_order_form_field_overrides_detection(client, alice):
    response = upload(client, alice, data=b"01/02/2026, 10:00 - Alex: a\n01/03/2026, 10:00 - Sam: b\n", date_order="month_first")

    conversation = response.json()["conversation"]
    assert (conversation["date_order"], conversation["first_message_at"]) == ("month_first", "2026-01-02T10:00:00")
    assert response.json()["warnings"] == []


def test_unknown_date_order_is_rejected(client, alice):
    assert upload(client, alice, date_order="dmy").status_code == 422


def test_import_without_a_token_is_401_and_stores_nothing(client, alice):
    assert upload(client, headers={}).status_code == 401
    assert upload(client, headers={}, data=b"x" * (MB5 + 1)).status_code == 401  # auth comes before the size check

    assert client.get("/api/conversations", headers=alice).json() == []


def test_content_decides_not_the_content_type(client, alice):
    assert upload(client, alice, content_type="application/pdf").status_code == 201
    assert upload(client, alice, filename="other.txt", data=b"\x89PNG\r\n\x1a\n\x00\x00").status_code == 422


@pytest.mark.parametrize(
    "filename, data, detail",
    [
        ("chat.pdf", CHAT.encode(), ".txt"),
        ("x" * 252 + ".txt", CHAT.encode(), "longer than 255"),
        (FILENAME, b"", "empty"),
        (FILENAME, b"\xff\xfe1\x000\x00", "not UTF-8"),
        (FILENAME, b"10/10/2026, 21:01 - Alex: hi\x00", "binary"),
        (FILENAME, b"hello there", "No WhatsApp messages"),
    ],
    ids=["not-txt", "name-too-long", "empty", "not-utf8", "nul-byte", "not-a-chat"],
)
def test_invalid_uploads_get_422_with_a_readable_detail(client, alice, filename, data, detail):
    response = upload(client, alice, data=data, filename=filename)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str) and detail in response.json()["detail"]
    assert client.get("/api/conversations", headers=alice).json() == []


def test_exactly_5_mb_is_accepted_and_one_byte_more_is_rejected(client, alice):
    header = b"10/10/2026, 21:01 - Alex: "
    exactly_5_mb = header + b"x" * (MB5 - len(header))
    assert len(exactly_5_mb) == MB5

    accepted = upload(client, alice, data=exactly_5_mb)
    rejected = upload(client, alice, data=exactly_5_mb + b"y", filename="other.txt")

    assert accepted.status_code == 201
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "The file is larger than 5 MB."}
    assert len(client.get("/api/conversations", headers=alice).json()) == 1


def test_the_same_file_twice_is_409_but_another_user_may_import_it(client, alice, bob):
    assert upload(client, alice).status_code == 201

    again = upload(client, alice, data=CHAT.replace("\n", "\r\n").encode())  # same chat, Windows line endings

    assert again.status_code == 409
    assert "already been imported" in again.json()["detail"]
    assert upload(client, bob).status_code == 201


def test_a_failed_import_is_rolled_back(client, alice, monkeypatch, db_session_factory):
    real_add = conversation_repository.add_conversation

    def add_then_fail(*args, **kwargs):
        real_add(*args, **kwargs)  # conversation and messages are flushed...
        raise RuntimeError("simulated failure before commit")

    monkeypatch.setattr(conversation_repository, "add_conversation", add_then_fail)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/conversations/import", files={"file": (FILENAME, CHAT.encode(), "text/plain")}, headers=alice,
    )

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert client.get("/api/conversations", headers=alice).json() == []
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0


def test_importing_does_not_log_message_text(client, alice, caplog):
    secret = "SECRET-MESSAGE-TEXT-4f9a"
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="sqlalchemy")  # SQLAlchemy sets its own logger to WARNING

    response = upload(client, alice, data=f"10/10/2026, 21:01 - Alex: {secret}\n10/10/2026, 21:02 - Sam: ok\n".encode())

    assert response.status_code == 201
    assert "INSERT INTO messages" in caplog.text  # logging really was on, down to SQL statements
    assert secret not in caplog.text


# ---------- list, detail, messages ----------

def test_a_user_without_conversations_gets_200_and_an_empty_list(client, alice):
    response = client.get("/api/conversations", headers=alice)

    assert (response.status_code, response.json()) == (200, [])


def test_list_shows_only_the_users_conversations_newest_first(client, alice, bob):
    older = upload(client, alice).json()["conversation"]["id"]
    newer = upload(client, alice, data=b"10/10/2026, 22:00 - Alex: another chat").json()["conversation"]["id"]
    upload(client, bob)

    assert [c["id"] for c in client.get("/api/conversations", headers=alice).json()] == [newer, older]


def test_detail_includes_participants_without_system_messages(client, alice):
    conversation_id = upload(client, alice).json()["conversation"]["id"]

    body = client.get(f"/api/conversations/{conversation_id}", headers=alice).json()

    assert body["id"] == conversation_id
    assert body["participants"] == [{"name": "Alex", "message_count": 1}, {"name": "Sam", "message_count": 1}]


def test_messages_keep_export_order_and_system_messages(client, alice):
    chat = (
        "25/10/2026, 2:50 AM - Alex: before the clocks went back\n"
        "25/10/2026, 2:05 AM - Sam: after the clocks went back\n"
        "25/10/2026, 2:05 AM - Alex left\n"
    )
    conversation_id = upload(client, alice, data=chat.encode()).json()["conversation"]["id"]

    body = client.get(f"/api/conversations/{conversation_id}/messages", headers=alice).json()

    assert body["items"] == [
        {"position": 0, "sent_at": "2026-10-25T02:50:00", "sender": "Alex", "content": "before the clocks went back"},
        {"position": 1, "sent_at": "2026-10-25T02:05:00", "sender": "Sam", "content": "after the clocks went back"},
        {"position": 2, "sent_at": "2026-10-25T02:05:00", "sender": None, "content": "Alex left"},
    ]
    assert (body["total"], body["offset"], body["limit"]) == (3, 0, 200)


def test_message_pages(client, alice):
    chat = "".join(f"10/10/2026, 21:{i:02d} - Alex: m{i}\n" for i in range(7))
    conversation_id = upload(client, alice, data=chat.encode()).json()["conversation"]["id"]
    url = f"/api/conversations/{conversation_id}/messages"

    def page(**params):
        return client.get(url, params=params, headers=alice)

    assert [m["position"] for m in page(offset=0, limit=3).json()["items"]] == [0, 1, 2]
    assert [m["position"] for m in page(offset=3, limit=3).json()["items"]] == [3, 4, 5]
    assert [m["position"] for m in page(offset=6, limit=3).json()["items"]] == [6]
    past_the_end = page(offset=7, limit=3)
    assert (past_the_end.status_code, past_the_end.json()["items"], past_the_end.json()["total"]) == (200, [], 7)
    assert page(limit=500).status_code == 200
    for bad in ({"limit": 501}, {"limit": 0}, {"offset": -1}):
        assert page(**bad).status_code == 422


# ---------- ownership and deletion ----------

def test_another_user_gets_404_everywhere_like_for_a_missing_conversation(client, alice, bob):
    conversation_id = upload(client, alice).json()["conversation"]["id"]

    for target in (conversation_id, conversation_id + 1000):
        for method, path in [
            ("GET", f"/api/conversations/{target}"),
            ("GET", f"/api/conversations/{target}/messages"),
            ("DELETE", f"/api/conversations/{target}"),
        ]:
            response = client.request(method, path, headers=bob)
            assert (response.status_code, response.json()) == (404, {"detail": "Conversation not found."})

    assert client.get(f"/api/conversations/{conversation_id}", headers=alice).status_code == 200
    assert client.get("/api/conversations", headers=bob).json() == []


def test_conversation_endpoints_require_a_token(client, alice):
    conversation_id = upload(client, alice).json()["conversation"]["id"]

    for method, path in [
        ("GET", "/api/conversations"),
        ("GET", f"/api/conversations/{conversation_id}"),
        ("GET", f"/api/conversations/{conversation_id}/messages"),
        ("DELETE", f"/api/conversations/{conversation_id}"),
    ]:
        response = client.request(method, path)
        assert (response.status_code, response.json()) == (401, {"detail": "Not authenticated"})


def test_delete_returns_204_removes_the_messages_and_then_404(client, alice, db_session_factory):
    conversation_id = upload(client, alice).json()["conversation"]["id"]

    deleted = client.delete(f"/api/conversations/{conversation_id}", headers=alice)

    assert (deleted.status_code, deleted.content) == (204, b"")
    assert client.get(f"/api/conversations/{conversation_id}", headers=alice).status_code == 404
    assert client.delete(f"/api/conversations/{conversation_id}", headers=alice).status_code == 404
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0


# ---------- concurrency (file-based SQLite by default; PostgreSQL with -m postgres) ----------

@pytest.fixture(params=["sqlite-file", pytest.param("postgres", marks=pytest.mark.postgres)])
def concurrent_db(request, tmp_path):
    """A database where concurrent requests get their own connections."""
    if request.param == "postgres":
        session_factory = sessionmaker(bind=request.getfixturevalue("migrated_postgres"), autoflush=False)
        engine = None
    else:
        engine = create_engine(
            f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False}, hide_parameters=True
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session_factory
    app.dependency_overrides.clear()
    if engine is not None:
        engine.dispose()


def test_concurrent_uploads_of_the_same_file_store_one_conversation(concurrent_db, monkeypatch):
    client = TestClient(app)
    headers = login(client)
    both_checked = threading.Barrier(2, timeout=10)

    def parse_after_both_passed_the_duplicate_check(text, date_order=None):
        both_checked.wait()
        return whatsapp.parse_whatsapp_chat(text, date_order)

    monkeypatch.setattr(conversation_service, "parse_whatsapp_chat", parse_after_both_passed_the_duplicate_check)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: upload(client, headers), range(2)))

    assert sorted(r.status_code for r in responses) == [201, 409]
    assert [r.json()["detail"] for r in responses if r.status_code == 409][0].startswith("This chat has already been imported")
    with concurrent_db() as db:
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 3


# ---------- full flow on PostgreSQL ----------

@pytest.mark.postgres
def test_full_flow_on_postgres(migrated_postgres):
    session_factory = sessionmaker(bind=migrated_postgres, autoflush=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        alice, bob = login(client, "alice@example.com"), login(client, "bob@example.com")
        assert client.get("/api/conversations", headers=alice).json() == []

        created = upload(client, alice)
        assert created.status_code == 201
        conversation_id = created.json()["conversation"]["id"]
        assert upload(client, alice).status_code == 409
        assert upload(client, alice, filename="nul.txt", data=b"10/10/2026, 21:01 - Alex: a\x00b").status_code == 422

        messages = client.get(f"/api/conversations/{conversation_id}/messages", headers=alice).json()
        assert [(m["position"], m["sender"]) for m in messages["items"]] == [(0, None), (1, "Alex"), (2, "Sam")]
        assert client.get(f"/api/conversations/{conversation_id}", headers=bob).status_code == 404
        assert client.delete(f"/api/conversations/{conversation_id}", headers=bob).status_code == 404

        assert client.delete(f"/api/conversations/{conversation_id}", headers=alice).status_code == 204
        with session_factory() as db:
            assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 0
    finally:
        app.dependency_overrides.clear()
