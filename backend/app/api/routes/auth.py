from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.api.schemas import LoginRequest, RegisterRequest
from app.auth import create_access_token
from app.models import User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    email = str(request.email).strip().lower()
    username = request.username.strip()

    if len(username) < 2:
        raise HTTPException(
            status_code=422,
            detail="Username must contain at least 2 non-space characters.",
        )

    existing_user = (
        db.query(User)
        .filter(func.lower(User.email) == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email is already registered.",
        )

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(request.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Registration successful.",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }


@router.post("/login")
def login_user(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    email = str(request.email).strip().lower()

    user = (
        db.query(User)
        .filter(func.lower(User.email) == email)
        .first()
    )

    if user is None or not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Login successful.",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }


@router.get("/me")
def get_my_profile(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
    }
