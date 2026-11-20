"""Baseline: the users table exactly as the app has created it since 714eeac.

The development database already has this table (built by init_db.py / create_all from the
same User model). It must be marked with `alembic stamp 0001`, never upgraded through this
revision, and only after a read-only check that its schema matches what this revision creates.
Stamping records a version number; it does not compare or validate any schema.

Revision ID: 0001
Revises:
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "Refusing to drop the users table: it holds real accounts. Restore from a backup instead."
    )
