"""Parser for WhatsApp "Export chat" text files (Android and iOS).

A line that starts with a timestamp starts a new entry; any other line continues the message
above it. An entry without "Sender: " is a system message (sender None). Times are kept exactly
as written: exports carry no time zone, so none is added.

Supported timestamps (the day/month order is detected per file, or given):
    10/10/2026, 9:30 PM - Alex: Hi       Android 12-hour (PM, pm, p.m., p. m., with or without a space)
    10/10/2026, 21:30 - Alex: Hi         Android 24-hour
    10.10.26 21:30 - Alex: Hi            dots or dashes, two-digit year, no comma
    [10/10/2026, 21:30:05] Alex: Hi      iOS, with seconds
Invisible direction marks and a BOM at the start of a line are ignored.

Years: exactly two digits become 2000 + yy (00 -> 2000, 09 -> 2009, 26 -> 2026, 99 -> 2099);
four digits are taken literally.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.entities import DateOrder, Message, ParsedChat

DATE_ORDERS: tuple[DateOrder, ...] = ("day_first", "month_first")

_MARKS = "\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff"  # direction marks, isolates, BOM
_LEADING_JUNK = re.compile(rf"^[\s{_MARKS}]+")
_DATE = r"(?P<d1>\d{1,2})(?P<sep>[./-])(?P<d2>\d{1,2})(?P=sep)(?P<year>\d{4}|\d{2})"
_TIME = (
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
    r"(?:\s*(?P<ampm>[AaPp]\.?\s?[Mm]\.?))?"
)
_ANDROID_LINE = re.compile(rf"{_DATE},?\s+{_TIME}\s+-\s(?P<rest>.*)")
_IOS_LINE = re.compile(rf"\[{_DATE},?\s+{_TIME}\]\s(?P<rest>.*)")


@dataclass
class _Entry:
    """A line that starts a chat entry, kept until the file's date order is known."""

    d1: int  # first and second date number: day/month or month/day
    d2: int
    year: int
    hour: int
    minute: int
    second: int
    sender: str | None
    lines: list[str] = field(default_factory=list)  # first line of text, then continuation lines

    def timestamp(self, order: DateOrder) -> datetime | None:
        day, month = (self.d1, self.d2) if order == "day_first" else (self.d2, self.d1)
        try:
            return datetime(self.year, month, day, self.hour, self.minute, self.second)
        except ValueError:
            return None


def _entry_from(match: re.Match[str]) -> _Entry | None:
    """Turn a timestamped line into an entry; None if its time is impossible or its sender empty."""
    hour, minute, second = int(match["hour"]), int(match["minute"]), int(match["second"] or 0)
    if match["ampm"]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if match["ampm"][0] in "Pp" else 0)
    if hour > 23 or minute > 59 or second > 59:
        return None

    year = int(match["year"]) + (2000 if len(match["year"]) == 2 else 0)
    sender, separator, text = match["rest"].partition(": ")
    if separator:
        sender = _LEADING_JUNK.sub("", sender).rstrip()
        if not sender:
            return None
    else:
        sender, text = None, match["rest"]  # system message: the whole rest is its text
    first_line = _LEADING_JUNK.sub("", text)
    return _Entry(int(match["d1"]), int(match["d2"]), year, hour, minute, second, sender, [first_line])


def _backward_steps(entries: list[_Entry], order: DateOrder) -> int:
    times = [t for t in (entry.timestamp(order) for entry in entries) if t is not None]
    return sum(later < earlier for earlier, later in zip(times, times[1:]))


def _choose_date_order(entries: list[_Entry], override: DateOrder | None) -> tuple[DateOrder, bool]:
    """Pick the date order for the whole file. The bool is True when day_first was only assumed."""
    if override is not None:
        return override, False
    if all(entry.d1 == entry.d2 for entry in entries):
        return "day_first", False  # both readings give the same dates
    possible = {order: sum(e.timestamp(order) is not None for e in entries) for order in DATE_ORDERS}
    if possible["day_first"] != possible["month_first"]:
        return max(DATE_ORDERS, key=possible.__getitem__), False  # a number above 12 decides
    backwards = {order: _backward_steps(entries, order) for order in DATE_ORDERS}
    if backwards["day_first"] != backwards["month_first"]:
        return min(DATE_ORDERS, key=backwards.__getitem__), False  # the reading that stays in time order
    return "day_first", True


def parse_whatsapp_chat(text: str, date_order: DateOrder | None = None) -> ParsedChat:
    """Parse an exported chat. date_order ("day_first"/"month_first") overrides detection."""
    if date_order is not None and date_order not in DATE_ORDERS:
        raise ValueError(f"date_order must be one of {DATE_ORDERS}, not {date_order!r}")

    entries: list[_Entry] = []
    current: _Entry | None = None  # the message that continuation lines belong to
    skipped = 0
    for line in text.splitlines():
        candidate = _LEADING_JUNK.sub("", line)
        match = _ANDROID_LINE.fullmatch(candidate) or _IOS_LINE.fullmatch(candidate)
        if match is None:
            if current is not None:
                current.lines.append(line)
            elif line.strip():
                skipped += 1  # text before the first message, or after a system/broken entry
            continue
        entry = _entry_from(match)
        if entry is None:
            skipped += 1
        else:
            entries.append(entry)
        current = entry if entry is not None and entry.sender is not None else None

    order, ambiguous = _choose_date_order(entries, date_order)
    warnings: list[str] = []
    if ambiguous:
        warnings.append(
            "The date order is ambiguous: no day is above 12 and both readings keep the messages "
            "in time order. Dates were read day first (dd/mm); if they look wrong, import the chat "
            "again choosing month first."
        )

    messages: list[Message] = []
    impossible_dates = 0
    for entry in entries:
        timestamp = entry.timestamp(order)
        content = "\n".join(line.rstrip() for line in entry.lines).strip()
        if timestamp is None:
            impossible_dates += 1
            skipped += 1 + sum(1 for line in entry.lines[1:] if line.strip())
        elif not content:
            skipped += 1
        else:
            messages.append(Message(timestamp=timestamp, sender=entry.sender, content=content))
    if impossible_dates:
        reading = "day first" if order == "day_first" else "month first"
        warnings.append(
            f"Skipped {impossible_dates} message(s) whose date does not exist when read {reading}."
        )

    return ParsedChat(
        messages=tuple(messages),
        detected_date_order=order,
        date_order_ambiguous=ambiguous,
        skipped_line_count=skipped,
        warnings=tuple(warnings),
    )
