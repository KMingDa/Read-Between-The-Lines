"""Rules for imported chat exports: duplicate fingerprints and display titles. Pure Python."""

import hashlib
import re
from collections.abc import Sequence
from pathlib import PurePath

MAX_TITLE_LENGTH = 255
_ANDROID_EXPORT_NAME = re.compile(r"WhatsApp Chat with (?P<name>.+)\.txt", re.IGNORECASE)


def fingerprint(text: str) -> str:
    """SHA-256 (hex) of an export, so uploading the same file twice is detected.

    These normalisations apply to the fingerprint only; message content is never changed:
    a leading BOM is dropped, CRLF and lone CR become LF, and whitespace at the very end of
    the file is removed. Nothing else is normalised (no Unicode normalisation, no changes
    inside lines), so any change to the text gives a different fingerprint.
    """
    normalised = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def derive_title(filename: str, senders: Sequence[str]) -> str:
    """Display title for an imported chat.

    The contact or group name from an Android export name ("WhatsApp Chat with Alex.txt"),
    else up to three senders, most active first ("Alex, Sam & 2 others"), else the file name
    without its extension. A title longer than 255 characters ends in "…"; the names stored
    with the messages are never shortened.
    """
    match = _ANDROID_EXPORT_NAME.fullmatch(filename)
    if match and match["name"].strip():
        title = match["name"].strip()
    elif senders:
        title = _join_names(senders)
    else:
        title = PurePath(filename).stem or "WhatsApp chat"
    return title if len(title) <= MAX_TITLE_LENGTH else title[: MAX_TITLE_LENGTH - 1] + "…"


def _join_names(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    if len(names) == 3:
        return f"{names[0]}, {names[1]} & {names[2]}"
    return f"{names[0]}, {names[1]} & {len(names) - 2} others"
