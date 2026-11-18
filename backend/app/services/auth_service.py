"""Registration, login and resolving an access token to its user."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, ConflictError, InvalidInputError
from app.core.security import decode_access_token, hash_password, verify_password
from app.infrastructure import user_repository
from app.infrastructure.models import User

MIN_USERNAME_LENGTH = 2
EMAIL_TAKEN = "Email is already registered."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, email: str, username: str, password: str) -> User:
    """Create a user. Raises InvalidInputError for a blank username, ConflictError for a taken email."""
    email = normalize_email(email)
    username = username.strip()
    if len(username) < MIN_USERNAME_LENGTH:
        raise InvalidInputError(
            f"Username must contain at least {MIN_USERNAME_LENGTH} non-space characters."
        )
    if user_repository.get_user_by_email(db, email) is not None:
        raise ConflictError(EMAIL_TAKEN)

    user = User(email=email, username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent request registered the same email after our check above.
        if user_repository.get_user_by_email(db, email) is not None:
            raise ConflictError(EMAIL_TAKEN) from None
        raise
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Return the user for valid credentials. Raises AuthenticationError otherwise."""
    user = user_repository.get_user_by_email(db, normalize_email(email))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password.")
    return user


def get_user_for_token(db: Session, token: str) -> User:
    """Return the user a valid token belongs to. Raises AuthenticationError if the token
    is invalid or expired, or the user no longer exists."""
    user = user_repository.get_user_by_id(db, decode_access_token(token))
    if user is None:
        raise AuthenticationError("User no longer exists.")
    return user
