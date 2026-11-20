"""OpenAPI documentation of the conversation endpoints matches what they really return."""

import pytest

from app.main import app

ERROR = {"$ref": "#/components/schemas/ErrorResponse"}
VALIDATION_ERROR = {"$ref": "#/components/schemas/HTTPValidationError"}
CONVERSATION = "/api/conversations/{conversation_id}"

# 422 on detail, messages and delete is FastAPI's own validation of the path and query
# parameters (e.g. a non-integer conversation_id); it was already documented before.
DOCUMENTED = {
    ("post", "/api/conversations/import"): {"201": None, "401": ERROR, "409": ERROR, "413": ERROR, "422": "either"},
    ("get", "/api/conversations"): {"200": None, "401": ERROR},
    ("get", CONVERSATION): {"200": None, "401": ERROR, "404": ERROR, "422": VALIDATION_ERROR},
    ("get", CONVERSATION + "/messages"): {"200": None, "401": ERROR, "404": ERROR, "422": VALIDATION_ERROR},
    ("delete", CONVERSATION): {"204": None, "401": ERROR, "404": ERROR, "422": VALIDATION_ERROR},
}


def operation(method, path):
    return app.openapi()["paths"][path][method]


def schema_of(response):
    return response["content"]["application/json"]["schema"]


def example_of(method, path, status):
    return operation(method, path)["responses"][status]["content"]["application/json"]["example"]


@pytest.mark.parametrize("method, path", sorted(DOCUMENTED))
def test_operation_documents_exactly_its_status_codes(method, path):
    assert set(operation(method, path)["responses"]) == set(DOCUMENTED[(method, path)])


@pytest.mark.parametrize("method, path", sorted(DOCUMENTED))
def test_error_responses_document_the_detail_body(method, path):
    responses = operation(method, path)["responses"]
    for status, expected in DOCUMENTED[(method, path)].items():
        if expected == "either":
            assert schema_of(responses[status]) == {"anyOf": [ERROR, VALIDATION_ERROR]}
        elif expected is not None:
            assert schema_of(responses[status]) == expected
    assert responses["401"]["headers"]["WWW-Authenticate"]["schema"] == {"type": "string"}


def test_error_response_schema_is_a_required_string_detail():
    schemas = app.openapi()["components"]["schemas"]

    assert schemas["ErrorResponse"]["properties"] == {"detail": {"type": "string", "title": "Detail"}}
    assert schemas["ErrorResponse"]["required"] == ["detail"]
    assert "HTTPValidationError" in schemas  # the other half of the import 422 must resolve


def test_documented_examples_are_what_the_api_returns(client):
    client.post("/api/register", json={"email": "alice@example.com", "username": "alice", "password": "CorrectHorse1"})
    token = client.post("/api/login", json={"email": "alice@example.com", "password": "CorrectHorse1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def upload(data, name="WhatsApp Chat with Alex.txt"):
        return client.post("/api/conversations/import", files={"file": (name, data, "text/plain")}, headers=headers)

    chat = b"10/10/2026, 21:01 - Alex: hi\n"
    assert upload(chat).status_code == 201
    actual = {
        ("get", "/api/conversations", "401"): client.get("/api/conversations"),
        ("get", CONVERSATION, "404"): client.get("/api/conversations/999", headers=headers),
        ("get", CONVERSATION + "/messages", "404"): client.get("/api/conversations/999/messages", headers=headers),
        ("delete", CONVERSATION, "404"): client.delete("/api/conversations/999", headers=headers),
        ("post", "/api/conversations/import", "409"): upload(chat),
        ("post", "/api/conversations/import", "413"): upload(b"x" * (5 * 1024 * 1024 + 1), "big.txt"),
        ("post", "/api/conversations/import", "422"): upload(b"", "empty.txt"),
    }

    for (method, path, status), response in actual.items():
        assert str(response.status_code) == status
        assert response.json() == example_of(method, path, status)


def test_the_list_form_of_the_import_422_is_fastapis_validation_error(client):
    client.post("/api/register", json={"email": "alice@example.com", "username": "alice", "password": "CorrectHorse1"})
    token = client.post("/api/login", json={"email": "alice@example.com", "password": "CorrectHorse1"}).json()["access_token"]

    response = client.post("/api/conversations/import", headers={"Authorization": f"Bearer {token}"})  # no file

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
