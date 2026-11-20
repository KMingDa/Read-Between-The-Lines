"""Error bodies, for OpenAPI documentation. Every error the app raises is {"detail": "<message>"}."""

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


def error_response(description: str, example: str) -> dict[str, Any]:
    """OpenAPI entry for one error status: the {"detail": ...} body and a real example message."""
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"example": {"detail": example}}},
    }


UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {
        **error_response(
            "No bearer token, or the token is invalid or expired, or its user no longer exists.",
            "Not authenticated",
        ),
        "headers": {
            "WWW-Authenticate": {"description": "Always `Bearer`.", "schema": {"type": "string"}}
        },
    }
}
