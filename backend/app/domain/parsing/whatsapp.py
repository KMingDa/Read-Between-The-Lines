"""Parser for WhatsApp "Export chat" text files.

Supported line format: ``dd/mm/yyyy, h:mm AM - Sender: text``.
A line without that timestamp prefix continues the message above it.
"""

from datetime import datetime

from app.domain.entities import Message

TIMESTAMP_FORMAT = "%d/%m/%Y, %I:%M %p"


def _parse_entry_line(line: str) -> tuple[datetime, str | None, str] | None:
    """Split a line that starts a new chat entry into (timestamp, sender, first line of text).

    Returns None when the line has no timestamp prefix, i.e. it continues the previous message.
    The sender is None for entries that are not messages (system notices, missing sender).
    """
    stamp, separator, rest = line.partition(" - ")
    if not separator:
        return None
    try:
        timestamp = datetime.strptime(stamp.strip(), TIMESTAMP_FORMAT)
    except ValueError:
        return None

    sender, separator, text = rest.partition(": ")
    sender = sender.strip()
    if not separator or not sender:
        return timestamp, None, ""
    return timestamp, sender, text


def parse_whatsapp_chat(text: str) -> list[Message]:
    """Parse an exported chat into messages sorted by time.

    Lines that are not part of a message are skipped: text before the first message,
    system notices and anything following them, and messages whose text is empty.
    """
    messages: list[Message] = []
    current: tuple[datetime, str, list[str]] | None = None

    def finish_current() -> None:
        if current is None:
            return
        timestamp, sender, lines = current
        content = "\n".join(line.rstrip() for line in lines).strip()
        if content:
            messages.append(Message(timestamp=timestamp, sender=sender, content=content))

    for line in text.splitlines():
        entry = _parse_entry_line(line)
        if entry is None:
            if current is not None:
                current[2].append(line)
            continue

        finish_current()
        timestamp, sender, first_line = entry
        current = (timestamp, sender, [first_line]) if sender is not None else None

    finish_current()
    return sorted(messages, key=lambda message: message.timestamp)
