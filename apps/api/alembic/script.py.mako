"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Rules (.claude/rules/25-sqlalchemy.md): ``downgrade()`` is MANDATORY and must
undo ``upgrade()`` exactly; destructive operations (drop table/column, data
loss) need explicit human confirmation; ``CREATE INDEX CONCURRENTLY`` needs
``op.execute`` outside the transaction (``with op.get_context().autocommit_block()``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the schema change."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert the schema change (must mirror upgrade)."""
    ${downgrades if downgrades else "pass"}
