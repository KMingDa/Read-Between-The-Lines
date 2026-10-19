import sys

sys.path.insert(0, "backend")

from fastapi import HTTPException

from app.auth import create_access_token, get_user_id_from_token


# Generate a token for test user ID 1
token = create_access_token(1)

print("Token generated:", bool(token))

# Verify the token
user_id = get_user_id_from_token(token)
print("Correct user ID:", user_id)

# Test an invalid token
try:
    get_user_id_from_token("invalid.token.value")
    print("Invalid token rejected: False")
except HTTPException as error:
    print("Invalid token rejected:", error.status_code == 401)
