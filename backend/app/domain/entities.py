"""Plain data types for conversations. No framework or database code."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DateOrder = Literal["day_first", "month_first"]


@dataclass(frozen=True, slots=True)
class Message:
    timestamp: datetime  # clock time exactly as exported; no time zone
    sender: str | None  # None for a system message ("Alex left", "Messages are end-to-end encrypted")
    content: str


@dataclass(frozen=True, slots=True)
class ParsedChat:
    messages: tuple[Message, ...]  # in export order
    detected_date_order: DateOrder  # the order used; the override when one was given
    date_order_ambiguous: bool  # True when day_first was assumed without evidence
    skipped_line_count: int  # non-blank lines that were not part of any message
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplyInterval:
    replier: str
    replied_to: str
    minutes: float


@dataclass(frozen=True, slots=True)
class ReplyIntervalAnalysis:
    intervals: tuple[ReplyInterval, ...]
    average_minutes: float | None
