from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)
from app.core.security import create_access_token
from app.infrastructure.models import User
from app.services import auth_service

router = APIRouter(prefix="/api")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> RegisterResponse:
    user = auth_service.register_user(db, str(request.email), request.username, request.password)
    return RegisterResponse(
        message="Registration successful.",
        user=UserResponse.model_validate(user),
    )


@router.post("/login")
def login_user(
    request: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user = auth_service.authenticate_user(db, str(request.email), request.password)
    return LoginResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
        message="Login successful.",
        user=UserResponse.model_validate(user),
    )


@router.get("/me")
def get_my_profile(
    user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(user)
