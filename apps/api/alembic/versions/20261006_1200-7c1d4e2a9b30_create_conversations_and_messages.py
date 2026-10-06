"""create conversations and messages

Revision ID: 7c1d4e2a9b30
Revises:
Create Date: 2026-10-06 12:00:00

Rules (.claude/rules/25-sqlalchemy.md): ``downgrade()`` is MANDATORY and must
undo ``upgrade()`` exactly; destructive operations (drop table/column, data
loss) need explicit human confirmation; ``CREATE INDEX CONCURRENTLY`` needs
``op.execute`` outside the transaction (``with op.get_context().autocommit_block()``).

Roadmap api 1.1 — the first revision, on an empty database: both tables are new, so the
plain ``create_index`` / FK forms are safe (no populated-table patterns needed). Hand-written
from ``app/models/conversation.py`` and ``docs/design/db-design.md``. Applied by a named human
against dev (ADR-0013), never by an agent.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision: str = "7c1d4e2a9b30"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the schema change."""
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "title",
            sa.Unicode(length=200),
            server_default=sa.text("N'New conversation'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            mssql.DATETIME2(precision=3),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mssql.DATETIME2(precision=3),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        op.f("ix_conversations_updated_at"), "conversations", ["updated_at"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Unicode(length=20), nullable=False),
        sa.Column("content", sa.Unicode(), nullable=False),
        sa.Column("citations", sa.Unicode(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            mssql.DATETIME2(precision=3),
            server_default=sa.text("SYSUTCDATETIME()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "citations IS NULL OR ISJSON(citations) = 1",
            name=op.f("ck_messages_citations_json"),
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_messages_role")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Revert the schema change (must mirror upgrade)."""
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_conversations_updated_at"), table_name="conversations")
    op.drop_table("conversations")
