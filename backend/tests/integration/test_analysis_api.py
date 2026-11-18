from app.core.security import create_access_token
from app.infrastructure.models import User

CHAT = (
    "10/10/2026, 9:00 AM - Jamie: Hi\n"
    "10/10/2026, 9:05 AM - Jamie: You there?\n"
    "10/10/2026, 9:15 AM - Taylor: Yes!\n"
    "10/10/2026, 9:20 AM - Jamie: Great\n"
    "10/10/2026, 9:50 AM - Taylor: Sorry, busy\n"
)


def analyze(client, headers, conversation=CHAT, user_name="Jamie"):
    return client.post(
        "/api/analyze",
        json={"conversation": conversation, "user_name": user_name},
        headers=headers,
    )


def test_analyze_returns_exact_body(client, auth_headers):
    response = analyze(client, auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "observation": "Parsed 5 messages from the conversation.",
        "interpretation": (
            "Reply intervals describe the time between consecutive message turns by different "
            "senders. They do not establish a person's intentions or level of interest."
        ),
        "suggested_next_step": (
            "Review the message sequence and reply intervals in the context of the conversation."
        ),
        "is_demo": True,
        "parsed_message_count": 5,
        "reply_details": [
            {"from": "Taylor", "to": "Jamie", "minutes": 10.0},
            {"from": "Taylor", "to": "Jamie", "minutes": 30.0},
        ],
        "reply_times": [10.0, 30.0],
        "average_reply_time_minutes": 20.0,
    }


def test_analyze_rounds_average_to_two_decimals(client, auth_headers):
    chat = (
        "10/10/2026, 9:00 AM - Jamie: a\n"
        "10/10/2026, 9:01 AM - Taylor: b\n"
        "10/10/2026, 9:02 AM - Jamie: c\n"
        "10/10/2026, 9:03 AM - Taylor: d\n"
        "10/10/2026, 9:04 AM - Jamie: e\n"
        "10/10/2026, 9:06 AM - Taylor: f\n"
    )  # replies 1, 1, 2 -> 1.333...

    body = analyze(client, auth_headers, conversation=chat).json()

    assert body["average_reply_time_minutes"] == 1.33
    assert body["reply_times"] == [1.0, 1.0, 2.0]  # individual times are not rounded


def test_analyze_counts_multiline_messages_once(client, auth_headers):
    chat = (
        "10/10/2026, 9:00 AM - Jamie: line one\n"
        "line two\n"
        "10/10/2026, 9:07 AM - Taylor: reply\n"
    )

    body = analyze(client, auth_headers, conversation=chat).json()

    assert body["parsed_message_count"] == 2
    assert body["reply_times"] == [7.0]


def test_analyze_unparseable_text_returns_zero_messages(client, auth_headers):
    body = analyze(client, auth_headers, conversation="hello there").json()

    assert body["parsed_message_count"] == 0
    assert body["reply_details"] == []
    assert body["reply_times"] == []
    assert body["average_reply_time_minutes"] is None
    assert body["observation"] == "No valid WhatsApp messages could be parsed."
    assert body["is_demo"] is True


def test_analyze_unknown_user_name_returns_messages_but_no_intervals(client, auth_headers):
    body = analyze(client, auth_headers, user_name="Nobody").json()

    assert body["parsed_message_count"] == 5
    assert body["reply_times"] == []
    assert body["average_reply_time_minutes"] is None


def test_analyze_rejects_empty_user_name(client, auth_headers):
    assert analyze(client, auth_headers, user_name="").status_code == 422


def test_analyze_rejects_conversation_over_10000_chars(client, auth_headers):
    assert analyze(client, auth_headers, conversation="x" * 10001).status_code == 422


def test_analyze_without_token_is_401(client):
    response = analyze(client, headers={})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_analyze_with_invalid_token_is_401(client):
    response = analyze(client, headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token."}


def test_analyze_rejects_valid_token_of_deleted_user(client, auth_headers, db_session_factory):
    with db_session_factory() as db:
        db.query(User).delete()
        db.commit()

    response = analyze(client, auth_headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "User no longer exists."}


def test_analyze_rejects_valid_token_of_user_that_never_existed(client):
    response = analyze(client, headers={"Authorization": f"Bearer {create_access_token(999)}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "User no longer exists."}
