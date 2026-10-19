from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic import EmailStr
from fastapi import Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User
from app.security import hash_password, verify_password
from app.auth import create_access_token, get_current_user_id

from app.chat_analysis import (
    parse_chat_text,
    analyze_reply_intervals,
)

app = FastAPI(
    title="Read Between the Lines API",
    description="API for the AI Conversation Intelligence Assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)

    
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ConversationRequest(BaseModel):
    conversation: str = Field(min_length=1, max_length=10000)
    user_name: str = Field(min_length=1, max_length=100)


class AnalysisResponse(BaseModel):
    observation: str
    interpretation: str
    suggested_next_step: str
    is_demo: bool
    parsed_message_count: int
    reply_details: list[dict] = Field(default_factory=list)
    reply_times: list[float] = Field(default_factory=list)
    average_reply_time_minutes: float | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/register", status_code=status.HTTP_201_CREATED)
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



@app.post("/api/login")
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



@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze_conversation(request: ConversationRequest, current_user: int = Depends(get_current_user_id),):
    conversation = request.conversation.strip()

    messages = parse_chat_text(conversation)
    results = analyze_reply_intervals(
        messages,
        request.user_name
    )

    if not messages:
        observation = "No valid WhatsApp messages could be parsed."
        interpretation = (
            "The input may not match the supported WhatsApp TXT format. "
            "No conclusions can be drawn from the conversation yet."
        )
        suggested_next_step = (
            "Check that each message includes a date, time, sender, "
            "and message content in the expected format."
        )
    else:
        observation = (
            f"Parsed {len(messages)} messages from the conversation."
        )
        interpretation = (
            "Reply intervals describe the time between consecutive "
            "message turns by different senders. They do not establish "
            "a person's intentions or level of interest."
        )
        suggested_next_step = (
            "Review the message sequence and reply intervals "
            "in the context of the conversation."
        )

    return AnalysisResponse(
        observation=observation,
        interpretation=interpretation,
        suggested_next_step=suggested_next_step,
        is_demo=True,
        parsed_message_count=len(messages),
        reply_details=results["reply_details"],
        reply_times=results["reply_times"],
        average_reply_time_minutes=(
            round(results["average_reply_time"], 2)
            if results["average_reply_time"] is not None
            else None
        ),
    )

@app.get("/api/me")
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