"""SQLAlchemy table mappings. Schema changes go through Alembic (backend/migrations)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# Imported message times are naive: WhatsApp exports carry the sender's local clock time and
# no time zone, so they are stored exactly as written. Intervals across a daylight-saving
# change can therefore be off by the size of that change.


class Conversation(Base):
    """One imported chat export, owned by one user."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_conversations_user_id_content_hash"),
        CheckConstraint("date_order IN ('day_first', 'month_first')", name="ck_conversations_date_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(20), server_default="whatsapp")
    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 of the normalised export text
    message_count: Mapped[int]  # every stored message, system messages included
    first_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))  # earliest sent_at
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))  # latest sent_at
    date_order: Mapped[str] = mapped_column(String(11))  # how the export's dates were read
    date_order_ambiguous: Mapped[bool]  # True when day_first was assumed without evidence
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    """One message of an imported conversation. sender is None for system messages."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_messages_conversation_id_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    # 0-based export order: the only message order. Never sort by sent_at; clock times repeat
    # and can go backwards (daylight saving).
    position: Mapped[int]
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    sender: Mapped[str | None] = mapped_column(Text)  # TEXT: parsed names have no length limit
    content: Mapped[str] = mapped_column(Text)
