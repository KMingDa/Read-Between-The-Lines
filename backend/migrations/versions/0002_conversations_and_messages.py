"""Conversations and messages for imported chats.

Message times (sent_at, first/last_message_at) are timestamp WITHOUT time zone: the clock
time exactly as written in the export, which has no time zone. imported_at is a real
instant and keeps its time zone. messages.position (0-based export order) is the message
order; date_order records how the export's dates were read and whether that was assumed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), server_default="whatsapp", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("first_message_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("date_order", sa.String(length=11), nullable=False),
        sa.Column("date_order_ambiguous", sa.Boolean(), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_conversations_user_id_content_hash"),
        sa.CheckConstraint(
            "date_order IN ('day_first', 'month_first')", name="ck_conversations_date_order"
        ),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("sender", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "position", name="uq_messages_conversation_id_position"),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
