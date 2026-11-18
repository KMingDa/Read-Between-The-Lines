"""Queries for the users table."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.models import User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by an already-normalised (lower-case) email."""
    # lower() on the column also matches rows stored before emails were normalised.
    return db.scalars(select(User).where(func.lower(User.email) == email)).first()
