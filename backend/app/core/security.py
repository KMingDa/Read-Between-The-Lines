"""Password hashing (Argon2) and access tokens (JWT)."""

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, get_settings
from app.core.exceptions import AuthenticationError

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expires_at}
    return jwt.encode(payload, get_settings().jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Return the user id in a valid, unexpired token; raise AuthenticationError otherwise."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},  # a token without exp would never expire
        )
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise jwt.InvalidTokenError("Invalid subject")
        user_id = int(subject)
    except (jwt.InvalidTokenError, ValueError):
        raise AuthenticationError("Invalid or expired token.") from None

    if user_id <= 0:
        raise AuthenticationError("Invalid or expired token.")
    return user_id
