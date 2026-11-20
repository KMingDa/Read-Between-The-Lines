"""Conversation analysis: parse an exported chat and measure reply intervals."""

from dataclasses import dataclass

from app.domain.entities import ReplyIntervalAnalysis
from app.domain.metrics import analyze_reply_intervals
from app.domain.parsing.whatsapp import parse_whatsapp_chat


@dataclass(frozen=True, slots=True)
class ConversationAnalysis:
    message_count: int
    reply_intervals: ReplyIntervalAnalysis
    observation: str
    interpretation: str
    suggested_next_step: str
    is_demo: bool = True  # interpretation and next step are fixed text, not generated


def analyze_conversation(conversation: str, user_name: str) -> ConversationAnalysis:
    parsed = parse_whatsapp_chat(conversation.strip())
    messages = [message for message in parsed.messages if message.sender is not None]  # not system
    reply_intervals = analyze_reply_intervals(messages, user_name)

    if not messages:
        return ConversationAnalysis(
            message_count=0,
            reply_intervals=reply_intervals,
            observation="No valid WhatsApp messages could be parsed.",
            interpretation=(
                "The input may not match the supported WhatsApp TXT format. "
                "No conclusions can be drawn from the conversation yet."
            ),
            suggested_next_step=(
                "Check that each message includes a date, time, sender, "
                "and message content in the expected format."
            ),
        )

    return ConversationAnalysis(
        message_count=len(messages),
        reply_intervals=reply_intervals,
        observation=f"Parsed {len(messages)} messages from the conversation.",
        interpretation=(
            "Reply intervals describe the time between consecutive "
            "message turns by different senders. They do not establish "
            "a person's intentions or level of interest."
        ),
        suggested_next_step=(
            "Review the message sequence and reply intervals "
            "in the context of the conversation."
        ),
    )
