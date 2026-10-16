
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze_conversation(request: ConversationRequest):
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
