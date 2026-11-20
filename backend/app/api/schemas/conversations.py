from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict

from app.domain.entities import DateOrder
from app.services.conversation_service import ConversationOverview, ImportResult, MessageSlice


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source: str
    original_filename: str
    message_count: int
    first_message_at: datetime  # clock time as exported, no time zone
    last_message_at: datetime
    date_order: DateOrder
    date_order_ambiguous: bool
    imported_at: datetime


class Participant(BaseModel):
    name: str
    message_count: int


class ConversationDetail(ConversationSummary):
    participants: list[Participant]  # system messages are not counted

    @classmethod
    def from_overview(cls, overview: ConversationOverview) -> Self:
        summary = ConversationSummary.model_validate(overview.conversation)
        return cls(
            **summary.model_dump(),
            participants=[
                Participant(name=name, message_count=count) for name, count in overview.participants
            ],
        )


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int  # 0-based export order
    sent_at: datetime  # clock time as exported, no time zone
    sender: str | None  # None for a system message
    content: str


class MessagePage(BaseModel):
    items: list[MessageResponse]
    total: int
    offset: int
    limit: int

    @classmethod
    def from_slice(cls, page: MessageSlice, *, offset: int, limit: int) -> Self:
        return cls(
            items=[MessageResponse.model_validate(message) for message in page.messages],
            total=page.total,
            offset=offset,
            limit=limit,
        )


class ImportResponse(BaseModel):
    conversation: ConversationSummary
    detected_date_order: DateOrder
    date_order_ambiguous: bool
    skipped_line_count: int
    warnings: list[str]

    @classmethod
    def from_result(cls, result: ImportResult) -> Self:
        return cls(
            conversation=ConversationSummary.model_validate(result.conversation),
            detected_date_order=result.chat.detected_date_order,
            date_order_ambiguous=result.chat.date_order_ambiguous,
            skipped_line_count=result.chat.skipped_line_count,
            warnings=list(result.chat.warnings),
        )
