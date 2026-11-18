import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# Hash made by the pre-refactor app (pwdlib Argon2 defaults). Existing users' hashes look like this.
EXISTING_HASH = "$argon2id$v=19$m=65536,t=3,p=4$ss0iuqPQ4E1/cEGvHGBiVw$r6uXqdW6WF4ILVYQzRouf57rBgWVK1uNKiP4g2fdvms"


# ---------- passwords ----------

def test_password_hash_does_not_contain_password_and_verifies():
    hashed = hash_password("DemoPassword123!")

    assert "DemoPassword123!" not in hashed
    assert verify_password("DemoPassword123!", hashed)
    assert not verify_password("WrongPassword!", hashed)


def test_new_hashes_are_argon2id():
    assert hash_password("x").startswith("$argon2id$")


def test_same_password_hashes_differently_each_time():
    assert hash_password("same") != hash_password("same")  # salted


def test_hashes_from_before_the_refactor_still_verify():
    assert verify_password("existing-user-password-1", EXISTING_HASH)
    assert not verify_password("existing-user-password-2", EXISTING_HASH)


# ---------- tokens ----------

def test_token_round_trips_user_id():
    assert decode_access_token(create_access_token(42)) == 42


def test_token_uses_hs256_and_expires_after_30_minutes():
    token = create_access_token(7)

    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
    assert payload["sub"] == "7"
    assert 30 * 60 - 5 <= payload["exp"] - time.time() <= 30 * 60


def _token(payload, key=None, algorithm="HS256"):
    return jwt.encode(payload, key or get_settings().jwt_secret_key, algorithm=algorithm)


def _future():
    return datetime.now(timezone.utc) + timedelta(minutes=5)


@pytest.mark.parametrize(
    "make_token",
    [
        lambda: "invalid.token.value",
        lambda: "",
        lambda: _token({"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}),
        lambda: _token({"sub": "1", "exp": _future()}, key="some-other-secret-0123456789abcdef"),
        lambda: _token({"sub": "1", "exp": _future()}, algorithm="HS512"),
        lambda: jwt.encode({"sub": "1", "exp": _future()}, None, algorithm="none"),
        lambda: _token({"sub": 1, "exp": _future()}),          # sub must be a string
        lambda: _token({"sub": "abc", "exp": _future()}),      # not a number
        lambda: _token({"sub": "0", "exp": _future()}),        # not a positive id
        lambda: _token({"sub": "-3", "exp": _future()}),
        lambda: _token({"exp": _future()}),                    # missing sub
        lambda: _token({"sub": "1"}),                          # missing exp: would never expire
        lambda: _token({}),                                    # no claims at all
    ],
    ids=[
        "garbage", "empty", "expired", "wrong-secret", "hs512", "alg-none",
        "int-sub", "non-numeric-sub", "zero-sub", "negative-sub", "no-sub",
        "no-exp", "no-claims",
    ],
)
# The HS512 case signs with our HS256-sized secret on purpose; PyJWT warns about that key size.
@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_bad_tokens_are_rejected(make_token):
    with pytest.raises(AuthenticationError, match="^Invalid or expired token.$"):
        decode_access_token(make_token())
