from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id
from app.api.schemas import AnalysisResponse, ConversationRequest
from app.chat_analysis import analyze_reply_intervals, parse_chat_text

router = APIRouter(prefix="/api")


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_conversation(
    request: ConversationRequest,
    current_user: int = Depends(get_current_user_id),
):
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
