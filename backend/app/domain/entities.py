"""Plain data types for conversations. No framework or database code."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Message:
    timestamp: datetime
    sender: str
    content: str


@dataclass(frozen=True, slots=True)
class ReplyInterval:
    replier: str
    replied_to: str
    minutes: float


@dataclass(frozen=True, slots=True)
class ReplyIntervalAnalysis:
    intervals: tuple[ReplyInterval, ...]
    average_minutes: float | None
