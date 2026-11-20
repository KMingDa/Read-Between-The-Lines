"""Queries for conversations and their messages.

Every query is scoped to the owning user, so another user's conversation looks exactly like a
missing one (None, [] or False). Nothing here commits: the caller owns the transaction and rolls
back after an error.
"""

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.domain.entities import ParsedChat
from app.infrastructure.models import Conversation, ConversationMessage


def add_conversation(
    db: Session,
    *,
    user_id: int,
    title: str,
    original_filename: str,
    content_hash: str,
    chat: ParsedChat,
) -> Conversation:
    """Insert a conversation and all its messages, keeping the export order as `position`.

    Raises ValueError for a chat without messages, and IntegrityError (at the flush) when this
    user already has a conversation with the same content_hash.
    """
    if not chat.messages:
        raise ValueError("A conversation needs at least one message.")

    sent_times = [message.timestamp for message in chat.messages]
    conversation = Conversation(
        user_id=user_id,
        title=title,
        original_filename=original_filename,
        content_hash=content_hash,
        message_count=len(chat.messages),
        first_message_at=min(sent_times),
        last_message_at=max(sent_times),
        date_order=chat.detected_date_order,
        date_order_ambiguous=chat.date_order_ambiguous,
    )
    db.add(conversation)
    db.flush()  # assigns conversation.id; the (user_id, content_hash) unique constraint fires here

    db.execute(  # one bulk INSERT for all messages
        insert(ConversationMessage),
        [
            {
                "conversation_id": conversation.id,
                "position": position,
                "sent_at": message.timestamp,
                "sender": message.sender,
                "content": message.content,
            }
            for position, message in enumerate(chat.messages)
        ],
    )
    return conversation


def get_conversation_by_hash(db: Session, user_id: int, content_hash: str) -> Conversation | None:
    return db.scalars(
        select(Conversation).where(
            Conversation.user_id == user_id, Conversation.content_hash == content_hash
        )
    ).first()


def get_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation | None:
    """None when the conversation does not exist or belongs to another user."""
    return db.scalars(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    ).first()


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    """The user's conversations, most recently imported first."""
    return list(db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.imported_at.desc(), Conversation.id.desc())
    ))


def _owned_messages(user_id: int, conversation_id: int):
    """Messages of one conversation, joined to it so only its owner can reach them."""
    return (
        select(ConversationMessage)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            Conversation.user_id == user_id,
        )
    )


def get_messages(
    db: Session, user_id: int, conversation_id: int, *, offset: int = 0, limit: int = 200
) -> list[ConversationMessage]:
    """A page of messages in export order; empty for another user's conversation."""
    return list(db.scalars(
        _owned_messages(user_id, conversation_id)
        .where(ConversationMessage.position >= offset)
        .order_by(ConversationMessage.position)
        .limit(limit)
    ))


def get_participants(db: Session, user_id: int, conversation_id: int) -> list[tuple[str, int]]:
    """(sender, message count) per sender, most messages first. System messages are left out."""
    message_count = func.count()
    rows = db.execute(
        _owned_messages(user_id, conversation_id)
        .with_only_columns(ConversationMessage.sender, message_count)
        .where(ConversationMessage.sender.is_not(None))
        .group_by(ConversationMessage.sender)
        .order_by(message_count.desc(), ConversationMessage.sender)
    )
    return [(sender, count) for sender, count in rows]


def delete_conversation(db: Session, user_id: int, conversation_id: int) -> bool:
    """Delete one of the user's conversations; its messages go with it (ON DELETE CASCADE)."""
    result = db.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    return result.rowcount == 1
