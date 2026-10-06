"""Conversation and message models (roadmap api 1.1 — ``docs/design/db-design.md``).

No database: the DDL is compiled for the SQL Server dialect and compared with what the
first Alembic revision renders offline, so the model and the migration cannot drift apart.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
from app.models import Conversation, Message
from app.models.conversation import DEFAULT_TITLE, ROLES, TITLE_MAX_LENGTH, _sql_literal

DIALECT = mssql.dialect()
INI = Path(__file__).resolve().parents[1] / "alembic.ini"
TEST_URL = (
    "mssql+aioodbc://u:p@db.invalid:1433/app"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)


def _ddl(table_name: str) -> str:
    return str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=DIALECT))


def _body_lines(create_table: str) -> set[str]:
    """The column/constraint lines of a CREATE TABLE, order-insensitive."""
    inner = create_table[create_table.index("(") + 1 : create_table.rindex(")")]
    return {line.strip().rstrip(",") for line in inner.splitlines() if line.strip()}


def test_models_register_both_tables_on_the_shared_metadata() -> None:
    assert Conversation.__table__ is Base.metadata.tables["conversations"]
    assert Message.__table__ is Base.metadata.tables["messages"]


def test_conversations_ddl_matches_the_design() -> None:
    ddl = _ddl("conversations")

    assert "id UNIQUEIDENTIFIER NOT NULL" in ddl
    assert f"title NVARCHAR({TITLE_MAX_LENGTH}) NOT NULL DEFAULT N'{DEFAULT_TITLE}'" in ddl
    assert "created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()" in ddl
    assert "updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()" in ddl
    assert "CONSTRAINT pk_conversations PRIMARY KEY (id)" in ddl


def test_messages_ddl_matches_the_design() -> None:
    ddl = _ddl("messages")

    assert "conversation_id UNIQUEIDENTIFIER NOT NULL" in ddl
    assert "role NVARCHAR(20) NOT NULL" in ddl
    assert "content NVARCHAR(max) NOT NULL" in ddl
    assert "citations NVARCHAR(max) NULL" in ddl
    assert "token_count INTEGER NULL" in ddl
    assert "CONSTRAINT ck_messages_role CHECK (role IN ('user', 'assistant'))" in ddl
    assert (
        "CONSTRAINT ck_messages_citations_json CHECK (citations IS NULL OR ISJSON(citations) = 1)"
        in ddl
    )
    assert (
        "CONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY(conversation_id) "
        "REFERENCES conversations (id)" in ddl
    )
    # no cascade: there is no delete feature (B8 #6) — SQL Server's NO ACTION applies
    assert "ON DELETE" not in ddl


def test_indexes_are_named_and_cover_list_and_thread_reads() -> None:
    rendered = {
        str(CreateIndex(index).compile(dialect=DIALECT))
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }
    assert rendered == {
        "CREATE INDEX ix_conversations_updated_at ON conversations (updated_at)",
        "CREATE INDEX ix_messages_conversation_id_created_at "
        "ON messages (conversation_id, created_at)",
    }


def test_python_side_defaults_give_an_id_and_the_default_title() -> None:
    id_default = Conversation.__table__.c.id.default
    title_default = Conversation.__table__.c.title.default

    assert isinstance(id_default.arg(None), UUID)
    assert title_default.arg == DEFAULT_TITLE
    assert isinstance(Message.__table__.c.id.default.arg(None), UUID)


def test_messages_load_oldest_first() -> None:
    order_by = Conversation.messages.property.order_by
    assert [str(column) for column in order_by] == ["messages.created_at"]


def test_role_check_is_built_from_the_roles_constant() -> None:
    assert f"CHECK (role IN ({', '.join(f"'{r}'" for r in ROLES)}))" in _ddl("messages")


def test_default_title_literal_escapes_quotes() -> None:
    assert _sql_literal("Team's chat") == "N'Team''s chat'"


def test_relationships_never_lazy_load() -> None:
    # an implicit lazy load on an AsyncSession would be a MissingGreenlet 500
    assert Conversation.messages.property.lazy == "raise"
    assert Message.conversation.property.lazy == "raise"


@pytest.mark.usefixtures("_restore_logging")
@pytest.mark.parametrize("table_name", ["conversations", "messages"])
def test_migration_creates_exactly_what_the_model_declares(
    monkeypatch: pytest.MonkeyPatch, table_name: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    output = io.StringIO()
    command.upgrade(Config(str(INI), output_buffer=output, stdout=io.StringIO()), "head", sql=True)

    match = re.search(rf"CREATE TABLE {table_name} \(.*?\n\)", output.getvalue(), re.DOTALL)
    assert match, f"the migration does not create {table_name}"
    assert _body_lines(match.group(0)) == _body_lines(_ddl(table_name))
