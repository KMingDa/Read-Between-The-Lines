"""The exact calls frontend/src/App.tsx makes, and the fields and types it reads back."""

CHAT = (
    "10/10/2026, 9:00 AM - Jamie: Hi\n"
    "10/10/2026, 9:15 AM - Taylor: Yes!\n"
)


def test_register_login_restore_session_and_analyze(client):
    email = "jamie@example.com"

    # handleAuth (register): username is the email local part; only `detail` is read on error.
    registered = client.post(
        "/api/register",
        json={"email": email, "username": email.split("@")[0], "password": "CorrectHorse1"},
    )
    assert registered.status_code == 201

    # handleAuth (login): reads result.user and result.access_token.
    login = client.post("/api/login", json={"email": email, "password": "CorrectHorse1"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert isinstance(token, str) and token
    user = login.json()["user"]
    assert isinstance(user["id"], int) and isinstance(user["email"], str) and isinstance(user["username"], str)

    headers = {"Authorization": f"Bearer {token}"}

    # restoreSession: GET /api/me must return the AuthUser shape.
    me = client.get("/api/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == user

    # handleAnalyze: reads every AnalysisResult field.
    analysis = client.post(
        "/api/analyze",
        json={"conversation": CHAT, "user_name": "Jamie"},
        headers={"Content-Type": "application/json", **headers},
    )
    assert analysis.status_code == 200
    body = analysis.json()
    for field in ("observation", "interpretation", "suggested_next_step"):
        assert isinstance(body[field], str)
    assert isinstance(body["is_demo"], bool)
    assert isinstance(body["parsed_message_count"], int)
    assert body["reply_details"] == [{"from": "Taylor", "to": "Jamie", "minutes": 15.0}]
    assert body["reply_times"] == [15.0]
    assert body["average_reply_time_minutes"] == 15.0


def test_auth_errors_have_a_string_detail_for_the_frontend(client, register):
    register()

    for response in (
        register(),  # duplicate email
        register(email="new@example.com", username=" a "),
        client.post("/api/login", json={"email": "alice@example.com", "password": "WrongHorse1"}),
    ):
        assert isinstance(response.json()["detail"], str)


def test_expired_session_gets_401_so_the_frontend_logs_out(client):
    # restoreSession and handleAnalyze treat 401 as "session expired".
    headers = {"Authorization": "Bearer expired-or-garbage"}

    assert client.get("/api/me", headers=headers).status_code == 401
    assert client.post(
        "/api/analyze", json={"conversation": CHAT, "user_name": "Jamie"}, headers=headers
    ).status_code == 401
