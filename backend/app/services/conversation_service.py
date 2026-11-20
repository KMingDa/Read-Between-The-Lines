"""Importing WhatsApp exports and managing a user's conversations. Owns every transaction.

The uploaded file is only held in memory while it is validated and parsed; it is never stored.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import PureWindowsPath

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, InvalidInputError, NotFoundError, PayloadTooLargeError
from app.domain.entities import DateOrder, ParsedChat
from app.domain.imports import derive_title, fingerprint
from app.domain.parsing.whatsapp import parse_whatsapp_chat
from app.infrastructure import conversation_repository
from app.infrastructure.models import Conversation, ConversationMessage

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_FILENAME_LENGTH = 255  # conversations.original_filename
NOT_FOUND = "Conversation not found."
ALREADY_IMPORTED = (
    "This chat has already been imported. To import it again (for example with a different "
    "date order), delete the existing conversation first."
)


@dataclass(frozen=True, slots=True)
class ImportResult:
    conversation: Conversation
    chat: ParsedChat  # the parser's report: date order, ambiguity, skipped lines, warnings


@dataclass(frozen=True, slots=True)
class ConversationOverview:
    conversation: Conversation
    participants: list[tuple[str, int]]  # (sender, message count), most messages first


@dataclass(frozen=True, slots=True)
class MessageSlice:
    total: int
    messages: list[ConversationMessage]


def import_whatsapp_export(
    db: Session,
    *,
    user_id: int,
    filename: str | None,
    data: bytes,
    date_order: DateOrder | None = None,
) -> ImportResult:
    """Validate, parse and store an uploaded export in a single transaction."""
    filename = _validated_filename(filename)
    text = _decoded_text(data)
    content_hash = fingerprint(text)
    if conversation_repository.get_conversation_by_hash(db, user_id, content_hash) is not None:
        raise ConflictError(ALREADY_IMPORTED)

    chat = parse_whatsapp_chat(text, date_order)  # the decoded text itself, not the fingerprint's copy
    senders = Counter(message.sender for message in chat.messages if message.sender is not None)
    if not senders:
        raise InvalidInputError(
            "No WhatsApp messages were found in this file. Upload the .txt file from "
            "WhatsApp's \"Export chat\" (Without media)."
        )

    try:
        conversation = conversation_repository.add_conversation(
            db,
            user_id=user_id,
            title=derive_title(filename, [name for name, _ in senders.most_common()]),
            original_filename=filename,
            content_hash=content_hash,
            chat=chat,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another upload of the same file was committed after the check above.
        if conversation_repository.get_conversation_by_hash(db, user_id, content_hash) is not None:
            raise ConflictError(ALREADY_IMPORTED) from None
        raise
    db.refresh(conversation)
    return ImportResult(conversation=conversation, chat=chat)


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    """The user's conversations, newest import first. An empty list is a normal answer."""
    return conversation_repository.list_conversations(db, user_id)


def get_conversation_detail(db: Session, user_id: int, conversation_id: int) -> ConversationOverview:
    conversation = _owned_conversation(db, user_id, conversation_id)
    participants = conversation_repository.get_participants(db, user_id, conversation_id)
    return ConversationOverview(conversation=conversation, participants=participants)


def get_message_page(
    db: Session, user_id: int, conversation_id: int, *, offset: int, limit: int
) -> MessageSlice:
    """Messages in export order. A page past the end is empty; the conversation must be the user's."""
    conversation = _owned_conversation(db, user_id, conversation_id)
    messages = conversation_repository.get_messages(
        db, user_id, conversation_id, offset=offset, limit=limit
    )
    return MessageSlice(total=conversation.message_count, messages=messages)


def delete_conversation(db: Session, user_id: int, conversation_id: int) -> None:
    if not conversation_repository.delete_conversation(db, user_id, conversation_id):
        raise NotFoundError(NOT_FOUND)
    db.commit()


def _owned_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation:
    conversation = conversation_repository.get_conversation(db, user_id, conversation_id)
    if conversation is None:
        raise NotFoundError(NOT_FOUND)  # also for another user's conversation: existence is not revealed
    return conversation


def _validated_filename(filename: str | None) -> str:
    name = PureWindowsPath(filename or "").name  # some browsers send a full path; keep the last part
    if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise InvalidInputError("The upload has no valid file name.")
    if len(name) > MAX_FILENAME_LENGTH:
        raise InvalidInputError(
            f"The file name is longer than {MAX_FILENAME_LENGTH} characters. Rename the file and try again."
        )
    if not name.lower().endswith(".txt"):
        raise InvalidInputError("Upload the exported .txt file (WhatsApp, Export chat, Without media).")
    return name


def _decoded_text(data: bytes) -> str:
    """The upload as text. Its content decides; the file name and Content-Type are not trusted."""
    if len(data) > MAX_IMPORT_BYTES:
        raise PayloadTooLargeError("The file is larger than 5 MB.")
    if not data:
        raise InvalidInputError("The file is empty.")
    try:
        text = data.decode("utf-8-sig")  # UTF-8, with or without a BOM
    except UnicodeDecodeError:
        raise InvalidInputError(
            "The file is not UTF-8 text. Export the chat again from WhatsApp (Without media) "
            "and upload the .txt file."
        ) from None
    if "\x00" in text:  # binary data; PostgreSQL text cannot store it either
        raise InvalidInputError("The file contains binary data, not a text chat export.")
    return text
