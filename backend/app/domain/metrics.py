"""Conversation metrics computed from parsed messages."""

from collections.abc import Sequence

from app.domain.entities import Message, ReplyInterval, ReplyIntervalAnalysis


def analyze_reply_intervals(messages: Sequence[Message], user_name: str) -> ReplyIntervalAnalysis:
    """Measure how long others take to reply to the user.

    A reply is a message from someone else directly after one of the user's messages.
    For a burst of messages from the user, the time counts from the last one.
    The user is matched by name, ignoring case and surrounding spaces.
    """
    ordered = sorted(messages, key=lambda message: message.timestamp)
    user = user_name.strip().casefold()

    intervals = tuple(
        ReplyInterval(
            replier=message.sender,
            replied_to=previous.sender,
            minutes=(message.timestamp - previous.timestamp).total_seconds() / 60,
        )
        for previous, message in zip(ordered, ordered[1:])
        if message.sender != previous.sender and previous.sender.strip().casefold() == user
    )
    average = sum(i.minutes for i in intervals) / len(intervals) if intervals else None
    return ReplyIntervalAnalysis(intervals=intervals, average_minutes=average)
