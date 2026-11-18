from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.auth import get_user_id_from_token
from app.database import SessionLocal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(
    token: str = Depends(oauth2_scheme),
) -> int:
    return get_user_id_from_token(token)
