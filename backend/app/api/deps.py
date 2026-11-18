from collections.abc import Iterator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.infrastructure.database import get_session_factory
from app.infrastructure.models import User
from app.services import auth_service

# Swagger "Authorize": paste the access_token from POST /api/login (it takes JSON, not a form).
bearer_scheme = HTTPBearer(description="Paste the access_token returned by POST /api/login.")


def get_db() -> Iterator[Session]:
    # Closing the session rolls back anything a request did not commit.
    with get_session_factory()() as db:
        yield db


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    return auth_service.get_user_for_token(db, credentials.credentials)
