from pydantic import BaseModel, EmailStr, Field


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
