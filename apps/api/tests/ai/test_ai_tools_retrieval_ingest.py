"""Tools (allow-listed read-only SQL), Azure AI Search retrieval, and the ingestion job —
all against fakes; ``pyodbc.connect`` and the network are never touched."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import app.ai.tools as registry
import app.ai.tools.queries as queries
from app.ai import ingest
from app.ai.tools.queries import InvalidQueryParams, QueryNotAllowed, register_query
from app.ai.tools.query_external_db import (
    TextToSqlDisabled,
    describe_queries,
    query_external_db,
    run_allowed_query,
    run_readonly_sql,
)
from app.ai.tools.retrieve import (
    CONTENT_FIELD,
    ID_FIELD,
    SOURCE_FIELD,
    TITLE_FIELD,
    VECTOR_FIELD,
    AzureSearchRetriever,
    NullRetriever,
)
from tests.ai.fakes import FakeEmbeddings, FakeSearchClient, FakeSession, fake_session_factory


@pytest.fixture(autouse=True)
def _reset_registries():
    queries._reset_for_tests()
    yield
    queries._reset_for_tests()


# ── allow-listed queries ─────────────────────────────────────────────────────


def test_register_query_refuses_non_select_and_unknown_types() -> None:
    with pytest.raises(ValueError, match="SELECT/WITH"):
        register_query("bad", sql="DELETE FROM t")
    with pytest.raises(ValueError, match="unsupported param type"):
        register_query("bad2", sql="SELECT 1", params={"x": "date"})


def test_run_allowed_query_binds_validated_params() -> None:
    register_query(
        "orders",
        sql="SELECT TOP (:limit) id FROM dbo.orders WHERE customer_id = :customer_id",
        params={"customer_id": "int", "limit": "int"},
        max_rows=2,
    )
    session = FakeSession(rows=[{"id": 1}, {"id": 2}, {"id": 3}])
    rows = asyncio.run(
        run_allowed_query(
            "orders", {"customer_id": 7, "limit": 5}, session_factory=fake_session_factory(session)
        )
    )
    assert rows == [{"id": 1}, {"id": 2}]  # capped at max_rows
    statement, params = session.executed[0]
    assert "customer_id = :customer_id" in statement
    assert params == {"customer_id": 7, "limit": 5}


def test_param_validation_is_strict() -> None:
    register_query("q", sql="SELECT :a AS a", params={"a": "int"})
    session = FakeSession()
    factory = fake_session_factory(session)
    with pytest.raises(InvalidQueryParams):
        asyncio.run(run_allowed_query("q", {"a": "1"}, session_factory=factory))  # wrong type
    with pytest.raises(InvalidQueryParams):
        asyncio.run(run_allowed_query("q", {"a": 1, "b": 2}, session_factory=factory))  # unknown
    with pytest.raises(InvalidQueryParams):
        asyncio.run(run_allowed_query("q", {"a": True}, session_factory=factory))  # bool ≠ int
    with pytest.raises(QueryNotAllowed):
        asyncio.run(run_allowed_query("missing", {}, session_factory=factory))
    assert session.executed == []


def test_text_to_sql_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_ALLOW_TEXT_TO_SQL", raising=False)
    session = FakeSession()
    with pytest.raises(TextToSqlDisabled):
        asyncio.run(run_readonly_sql("SELECT 1", session_factory=fake_session_factory(session)))
    monkeypatch.setenv("AI_ALLOW_TEXT_TO_SQL", "true")
    with pytest.raises(PermissionError):
        asyncio.run(run_readonly_sql("DROP TABLE t", session_factory=fake_session_factory(session)))
    asyncio.run(run_readonly_sql("SELECT 1", session_factory=fake_session_factory(session)))
    assert session.executed[0][0].strip() == "SELECT 1"


def test_langchain_tool_returns_json_and_safe_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    register_query("ping", sql="SELECT 1 AS one", description="health")
    session = FakeSession(rows=[{"one": 1}])
    import app.ai.tools.query_external_db as tool_mod

    monkeypatch.setattr(tool_mod, "get_external_sessionmaker", fake_session_factory(session))
    assert query_external_db.name == "query_external_db"
    assert any(t.name == "query_external_db" for t in registry.get_tools())

    ok = asyncio.run(query_external_db.ainvoke({"query_name": "ping", "params": "{}"}))
    assert json.loads(ok) == [{"one": 1}]
    bad = json.loads(asyncio.run(query_external_db.ainvoke({"query_name": "nope", "params": "{}"})))
    assert "not in the allow-list" in bad["error"]
    assert "ping" in bad["available"]
    malformed = json.loads(
        asyncio.run(query_external_db.ainvoke({"query_name": "ping", "params": "{"}))
    )
    assert "JSON" in malformed["error"]
    assert "ping(" in describe_queries()


# ── retrieval ────────────────────────────────────────────────────────────────


def test_null_retriever_returns_nothing() -> None:
    assert asyncio.run(NullRetriever().retrieve("q")) == []


def test_azure_search_retriever_runs_hybrid_query() -> None:
    client = FakeSearchClient(
        rows=[{ID_FIELD: "a", CONTENT_FIELD: "text a", SOURCE_FIELD: "s1", "@search.score": 1.5}]
    )
    embeddings = FakeEmbeddings(dimensions=3)
    retriever = AzureSearchRetriever(client, embeddings)
    chunks = asyncio.run(retriever.retrieve("hello", top_k=3))
    # no stored title (indexed before the field existed): the file name of the source
    assert chunks == [{"id": "a", "content": "text a", "source": "s1", "score": 1.5, "title": "s1"}]
    assert embeddings.queries == ["hello"]
    call = client.search_calls[0]
    assert call["search_text"] == "hello" and call["top"] == 3
    assert call["select"] == [ID_FIELD, CONTENT_FIELD, SOURCE_FIELD, TITLE_FIELD]
    vq = call["vector_queries"][0]
    assert (
        vq.fields == VECTOR_FIELD and vq.k_nearest_neighbors == 3 and vq.vector == [5.0, 0.0, 0.0]
    )


# ── ingestion ────────────────────────────────────────────────────────────────


def test_chunk_text_windows_with_overlap() -> None:
    assert ingest.chunk_text("") == []
    chunks = ingest.chunk_text("abcdefghij", size=4, overlap=1)
    assert chunks == ["abcd", "defg", "ghij"]
    with pytest.raises(ValueError):
        ingest.chunk_text("x", size=4, overlap=4)


def test_build_index_matches_the_retriever_contract() -> None:
    index = ingest.build_index("docs", dimensions=8)
    names = {f.name: f for f in index.fields}
    assert names[ID_FIELD].key is True
    assert names[CONTENT_FIELD].searchable is True
    assert names[VECTOR_FIELD].vector_search_dimensions == 8
    assert names[VECTOR_FIELD].vector_search_profile_name == ingest.VECTOR_PROFILE
    assert index.vector_search.profiles[0].algorithm_configuration_name == ingest.HNSW_CONFIG


def test_ingest_documents_embeds_and_uploads_in_batches() -> None:
    client = FakeSearchClient()
    embeddings = FakeEmbeddings(dimensions=2)
    docs = [ingest.IngestDocument(source="a.md", text="one two three four five six")]
    report = asyncio.run(
        ingest.ingest_documents(
            docs,
            embeddings=embeddings,
            search_client=client,
            chunk_size=10,
            overlap=2,
            batch_size=2,
        )
    )
    assert report.documents == 1 and report.chunks == report.uploaded > 1 and report.failed == 0
    assert len(client.uploaded) == -(-report.chunks // 2)  # ceil(chunks / batch_size)
    first = client.uploaded[0][0]
    assert set(first) == {
        ID_FIELD,
        CONTENT_FIELD,
        SOURCE_FIELD,
        TITLE_FIELD,
        ingest.CHUNK_INDEX_FIELD,
        VECTOR_FIELD,
    }
    assert first[ID_FIELD] == ingest.chunk_id("a.md", 0)
    assert len(first[VECTOR_FIELD]) == 2


def test_load_path_reads_text_files_only(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    (tmp_path / "c.bin").write_bytes(b"\x00")
    docs = ingest.load_path(tmp_path)
    assert [d.text for d in docs] == ["alpha", "beta"]
    assert ingest.load_path(tmp_path / "a.md")[0].source == "a.md"


# ── titles + citation paths (roadmap api 3.1) ────────────────────────────────


def test_azure_search_retriever_returns_the_stored_title() -> None:
    client = FakeSearchClient(
        rows=[
            {
                ID_FIELD: "a",
                CONTENT_FIELD: "text a",
                SOURCE_FIELD: "docs/a.md",
                TITLE_FIELD: "Alpha guide",
                "@search.score": 1.0,
            }
        ]
    )
    retriever = AzureSearchRetriever(client, FakeEmbeddings(dimensions=3))
    [chunk] = asyncio.run(retriever.retrieve("hello"))
    assert chunk["title"] == "Alpha guide"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# Team Assistant\n\nbody", "Team Assistant"),
        ("intro line\n\n#   Spaced title  \n", "Spaced title"),
        ("## Only a level-2 heading\ntext", "notes.md"),
        ("#hashtag is not a heading", "notes.md"),
        ("", "notes.md"),
    ],
)
def test_extract_title_uses_the_first_level_1_heading_else_the_file_name(
    text: str, expected: str
) -> None:
    assert ingest.extract_title(text, "docs/notes.md") == expected


def test_extract_title_is_capped() -> None:
    assert len(ingest.extract_title("# " + "x" * 500, "a.md")) == ingest.TITLE_MAX_LENGTH


def test_load_path_stores_paths_relative_to_the_folder_parent_and_titles(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    (docs_dir / "architecture").mkdir(parents=True)
    (docs_dir / "README.md").write_text("# Docs hub\n", encoding="utf-8")
    (docs_dir / "architecture" / "ai.md").write_text("no heading", encoding="utf-8")

    docs = ingest.load_path(docs_dir)

    # file order follows the filesystem sort (case-insensitive on Windows) — compare as a set
    assert {(d.source, d.title) for d in docs} == {
        ("docs/README.md", "Docs hub"),
        ("docs/architecture/ai.md", "ai.md"),
    }


def test_load_path_of_a_single_file_stores_its_name(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# Notes", encoding="utf-8")
    [doc] = ingest.load_path(tmp_path / "notes.md")
    assert (doc.source, doc.title) == ("notes.md", "Notes")


def test_build_index_has_a_searchable_title() -> None:
    names = {f.name: f for f in ingest.build_index("docs", dimensions=8).fields}
    assert names[TITLE_FIELD].searchable is True


def test_ingest_uploads_the_title_with_every_chunk() -> None:
    client = FakeSearchClient()
    docs = [ingest.IngestDocument(source="a.md", text="# Alpha\n" + "word " * 50, title="Alpha")]
    asyncio.run(
        ingest.ingest_documents(
            docs,
            embeddings=FakeEmbeddings(dimensions=2),
            search_client=client,
            chunk_size=40,
            overlap=5,
        )
    )
    uploaded = [record for batch in client.uploaded for record in batch]
    assert len(uploaded) > 1 and {r[TITLE_FIELD] for r in uploaded} == {"Alpha"}


class _OldIndexSearchClient(FakeSearchClient):
    """Rejects `select=title` the way an index built before the title field does."""

    def __init__(self, rows: list[dict[str, Any]], status: int = 400) -> None:
        super().__init__(rows=rows)
        self.status = status

    def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        from azure.core.exceptions import HttpResponseError

        self.search_calls.append(kwargs)
        if TITLE_FIELD in kwargs["select"]:
            error = HttpResponseError(message="Could not find a property named 'title'")
            error.status_code = self.status
            raise error
        return list(self.rows)


def test_retrieval_keeps_working_against_an_index_without_the_title_field() -> None:
    client = _OldIndexSearchClient(
        rows=[{ID_FIELD: "a", CONTENT_FIELD: "t", SOURCE_FIELD: "docs/a.md", "@search.score": 1.0}]
    )
    retriever = AzureSearchRetriever(client, FakeEmbeddings(dimensions=3))

    [first] = asyncio.run(retriever.retrieve("q"))
    asyncio.run(retriever.retrieve("q again"))

    assert first["title"] == "a.md"  # falls back to the file name
    selects = [call["select"] for call in client.search_calls]
    assert TITLE_FIELD in selects[0]  # tried once with the title
    assert all(TITLE_FIELD not in s for s in selects[1:])  # then remembered: no title
    assert len(selects) == 3  # first try, its retry, the second question


def test_retrieval_does_not_swallow_other_search_errors() -> None:
    from azure.core.exceptions import HttpResponseError

    client = _OldIndexSearchClient(rows=[], status=503)
    retriever = AzureSearchRetriever(client, FakeEmbeddings(dimensions=3))

    with pytest.raises(HttpResponseError):
        asyncio.run(retriever.retrieve("q"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("```bash\n# install deps\n```\n# Real title", "Real title"),
        ("~~~\n# not this\n~~~\nno heading", "notes.md"),
        ("---\ntitle: x\n# yaml comment\n---\n# After front matter", "After front matter"),
    ],
)
def test_extract_title_skips_code_blocks_and_front_matter(text: str, expected: str) -> None:
    assert ingest.extract_title(text, "docs/notes.md") == expected


def test_files_outside_the_ingested_folder_are_not_ingested(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("do not index", encoding="utf-8")

    # what a symlink inside docs/ pointing at ../secret.md resolves to
    assert ingest.display_path(outside, root) is None
    assert ingest.display_path(root / "a.md", root) == "docs/a.md"


def test_the_ingest_cli_loads_the_local_env_before_reading_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(ingest, "load_local_env", lambda: order.append("env"))
    monkeypatch.setattr(ingest, "configure_logging", lambda: order.append("logging"))

    async def fake_run(argv: Any) -> ingest.IngestReport:
        order.append("run")
        return ingest.IngestReport(documents=1, chunks=2, uploaded=2)

    monkeypatch.setattr(ingest, "run", fake_run)
    monkeypatch.setattr(ingest.sys, "argv", ["ingest", "docs"])

    ingest.main()

    assert order == ["env", "logging", "run"]
