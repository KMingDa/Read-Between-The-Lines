from app.auth import create_access_token, get_user_id_from_token
from app.models import User

CHAT = (
    "10/10/2026, 9:00 AM - Jamie: Hi\n"
    "10/10/2026, 9:05 AM - Jamie: You there?\n"
    "10/10/2026, 9:15 AM - Taylor: Yes!\n"
    "10/10/2026, 9:20 AM - Jamie: Great\n"
    "10/10/2026, 9:50 AM - Taylor: Sorry, busy\n"
)


def login(client, email="alice@example.com", password="CorrectHorse1"):
    return client.post("/api/login", json={"email": email, "password": password})


# ---------- health ----------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# ---------- register ----------

def test_register_creates_user_and_hides_password(register, db_session_factory):
    response = register()

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["username"] == "alice"
    assert "password" not in str(body).lower()

    with db_session_factory() as db:
        user = db.query(User).one()
        assert user.password_hash != "CorrectHorse1"


def test_register_stores_email_lowercase_and_trims_username(register):
    response = register(email="Alice@Example.COM", username="  alice  ")

    assert response.json()["user"]["email"] == "alice@example.com"
    assert response.json()["user"]["username"] == "alice"


def test_duplicate_email_is_rejected(register):
    register()

    response = register(username="other")

    assert response.status_code == 409
    assert response.json()["detail"] == "Email is already registered."


def test_duplicate_email_check_ignores_case(register):
    register()

    assert register(email="ALICE@example.com").status_code == 409


def test_username_of_only_spaces_padding_is_rejected(register):
    # Passes the 2-char schema check, then fails after strip().
    response = register(username=" a ")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_one_character_username_is_rejected(register):
    # The frontend sends the email local part as username, so "a@x.com" hits this.
    assert register(email="a@example.com", username="a").status_code == 422


def test_short_password_is_rejected(register):
    assert register(password="short").status_code == 422


def test_invalid_email_is_rejected(register):
    assert register(email="not-an-email").status_code == 422


# ---------- login ----------

def test_login_returns_token_for_that_user(client, register):
    user_id = register().json()["user"]["id"]

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == user_id
    assert get_user_id_from_token(body["access_token"]) == user_id


def test_login_email_is_case_insensitive(client, register):
    register()

    assert login(client, email="ALICE@Example.com").status_code == 200


def test_wrong_password_and_unknown_email_get_same_401(client, register):
    register()

    wrong_password = login(client, password="WrongPassword1")
    unknown_email = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid email or password."}


# ---------- GET /api/me ----------

def test_me_returns_current_user(client, auth_headers):
    response = client.get("/api/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"
    assert set(response.json()) == {"id", "email", "username"}


def test_me_returns_only_the_token_owner(client, register):
    register()
    register(email="bob@example.com", username="bob")
    bob_token = login(client, email="bob@example.com").json()["access_token"]

    response = client.get("/api/me", headers={"Authorization": f"Bearer {bob_token}"})

    assert response.json()["email"] == "bob@example.com"


def test_me_without_token_is_401(client):
    assert client.get("/api/me").status_code == 401


def test_me_with_invalid_token_is_401(client):
    response = client.get("/api/me", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_for_deleted_user_is_401(client, auth_headers, db_session_factory):
    with db_session_factory() as db:
        db.query(User).delete()
        db.commit()

    response = client.get("/api/me", headers=auth_headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "User no longer exists."


# ---------- POST /api/analyze ----------

def test_analyze_returns_reply_intervals(client, auth_headers):
    response = client.post(
        "/api/analyze",
        json={"conversation": CHAT, "user_name": "Jamie"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_message_count"] == 5
    assert body["reply_times"] == [10.0, 30.0]
    assert body["average_reply_time_minutes"] == 20.0
    assert body["reply_details"][0] == {"from": "Taylor", "to": "Jamie", "minutes": 10.0}
    assert body["is_demo"] is True


def test_analyze_rounds_average_to_two_decimals(client, auth_headers):
    chat = (
        "10/10/2026, 9:00 AM - Jamie: a\n"
        "10/10/2026, 9:01 AM - Taylor: b\n"
        "10/10/2026, 9:02 AM - Jamie: c\n"
        "10/10/2026, 9:03 AM - Taylor: d\n"
        "10/10/2026, 9:04 AM - Jamie: e\n"
        "10/10/2026, 9:06 AM - Taylor: f\n"
    )  # replies 1, 1, 2 -> 1.333...

    body = client.post(
        "/api/analyze", json={"conversation": chat, "user_name": "Jamie"}, headers=auth_headers
    ).json()

    assert body["average_reply_time_minutes"] == 1.33


def test_analyze_unparseable_text_returns_zero_messages(client, auth_headers):
    body = client.post(
        "/api/analyze",
        json={"conversation": "hello there", "user_name": "Jamie"},
        headers=auth_headers,
    ).json()

    assert body["parsed_message_count"] == 0
    assert body["reply_details"] == []
    assert body["average_reply_time_minutes"] is None
    assert body["observation"] == "No valid WhatsApp messages could be parsed."


def test_analyze_unknown_user_name_returns_messages_but_no_intervals(client, auth_headers):
    body = client.post(
        "/api/analyze", json={"conversation": CHAT, "user_name": "Nobody"}, headers=auth_headers
    ).json()

    assert body["parsed_message_count"] == 5
    assert body["reply_times"] == []
    assert body["average_reply_time_minutes"] is None


def test_analyze_rejects_empty_user_name(client, auth_headers):
    response = client.post(
        "/api/analyze", json={"conversation": CHAT, "user_name": ""}, headers=auth_headers
    )

    assert response.status_code == 422


def test_analyze_rejects_conversation_over_10000_chars(client, auth_headers):
    response = client.post(
        "/api/analyze",
        json={"conversation": "x" * 10001, "user_name": "Jamie"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_analyze_without_token_is_401(client):
    response = client.post("/api/analyze", json={"conversation": CHAT, "user_name": "Jamie"})

    assert response.status_code == 401


def test_analyze_with_invalid_token_is_401(client):
    response = client.post(
        "/api/analyze",
        json={"conversation": CHAT, "user_name": "Jamie"},
        headers={"Authorization": "Bearer nope"},
    )

    assert response.status_code == 401


def test_analyze_accepts_token_of_user_that_does_not_exist(client):
    # Documents a known gap: analyze checks the token only, not that the user exists.
    # When Step 3 adds the user check, flip this to expect 401.
    token = create_access_token(999)

    response = client.post(
        "/api/analyze",
        json={"conversation": CHAT, "user_name": "Jamie"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
