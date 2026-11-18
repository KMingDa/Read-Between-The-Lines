from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.auth import create_access_token, get_user_id_from_token
from app.core.config import JWT_SECRET_KEY
from app.security import hash_password, verify_password


def test_password_hash_does_not_contain_password_and_verifies():
    hashed = hash_password("DemoPassword123!")

    assert "DemoPassword123!" not in hashed
    assert verify_password("DemoPassword123!", hashed)
    assert not verify_password("WrongPassword!", hashed)


def test_same_password_hashes_differently_each_time():
    assert hash_password("same") != hash_password("same")  # salted


def test_token_round_trips_user_id():
    assert get_user_id_from_token(create_access_token(42)) == 42


def _token(payload):
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")


FUTURE = datetime.now(timezone.utc) + timedelta(minutes=5)


@pytest.mark.parametrize(
    "token",
    [
        "invalid.token.value",
        _token({"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}),  # expired
        jwt.encode({"sub": "1", "exp": FUTURE}, "some-other-secret-0123456789abcdef", algorithm="HS256"),
        _token({"sub": 1, "exp": FUTURE}),          # sub must be a string
        _token({"sub": "abc", "exp": FUTURE}),      # not a number
        _token({"sub": "0", "exp": FUTURE}),        # not a positive id
        _token({"exp": FUTURE}),                    # missing sub
    ],
    ids=["garbage", "expired", "wrong-secret", "int-sub", "non-numeric-sub", "zero-sub", "no-sub"],
)
def test_bad_tokens_are_rejected_with_401(token):
    with pytest.raises(HTTPException) as error:
        get_user_id_from_token(token)

    assert error.value.status_code == 401
