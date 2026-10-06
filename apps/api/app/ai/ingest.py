"""RAG ingestion job (ADR-0009): load → chunk → embed → upload to Azure AI Search.

Owns the **index definition** (``build_index``) so the retriever and the index never drift:
fields ``id`` (key), ``content`` (searchable), ``source`` (filterable), ``chunk_index``, and
``content_vector`` (HNSW vector profile, ``AZURE_AI_EMBEDDING_DIMENSIONS`` wide). ``ensure_index``
is idempotent (``create_or_update_index``).

Run it from ``apps/api`` (needs the AI + search settings; the api identity or a dev key with
*Search Index Data Contributor* + *Search Service Contributor*)::

    uv run python -m app.ai.ingest ./docs            # every .md/.txt under ./docs
    uv run python -m app.ai.ingest notes.md --chunk-size 800 --overlap 80

Batches are embedded with ``aembed_documents`` and uploaded with ``upload_documents``; the
report prints counts only — never content. Very large corpora deserve a real pipeline (an
indexer + skillset); this job is the starting point.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings

from app.ai.config import AISettings, get_ai_settings
from app.ai.tools.retrieve import (
    CONTENT_FIELD,
    ID_FIELD,
    SOURCE_FIELD,
    VECTOR_FIELD,
    build_search_client,
    build_search_credential,
)
from app.logging_config import configure_logging, get_logger

CHUNK_INDEX_FIELD = "chunk_index"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 100
VECTOR_PROFILE = "vector-profile"
HNSW_CONFIG = "hnsw"
TEXT_SUFFIXES = (".md", ".txt")


@dataclass(frozen=True)
class IngestDocument:
    source: str
    text: str


@dataclass
class IngestReport:
    documents: int = 0
    chunks: int = 0
    uploaded: int = 0
    failed: int = 0


def chunk_text(
    text: str, size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    """Fixed-size character windows with overlap; whitespace-only chunks are dropped."""
    if size <= 0:
        raise ValueError("size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    step = size - overlap
    for start in range(0, len(text), step):
        piece = text[start : start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(text):
            break
    return chunks


def chunk_id(source: str, index: int) -> str:
    """Stable, key-safe id (re-ingesting the same source overwrites the same documents)."""
    return hashlib.sha1(f"{source}#{index}".encode()).hexdigest()


def build_index(name: str, dimensions: int) -> Any:
    """The ``SearchIndex`` the retriever expects (keyword + vector fields, HNSW profile)."""
    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration,
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )

    fields = [
        SimpleField(name=ID_FIELD, type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name=CONTENT_FIELD),
        SimpleField(name=SOURCE_FIELD, type=SearchFieldDataType.String, filterable=True),
        SimpleField(
            name=CHUNK_INDEX_FIELD, type=SearchFieldDataType.Int32, filterable=True, sortable=True
        ),
        SearchField(
            name=VECTOR_FIELD,
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dimensions,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name=HNSW_CONFIG)],
        profiles=[
            VectorSearchProfile(name=VECTOR_PROFILE, algorithm_configuration_name=HNSW_CONFIG)
        ],
    )
    return SearchIndex(name=name, fields=fields, vector_search=vector_search)


def build_index_client(settings: AISettings | None = None) -> Any:
    from azure.search.documents.indexes import SearchIndexClient

    s = settings or get_ai_settings()
    s.require_search()
    return SearchIndexClient(endpoint=s.search_endpoint, credential=build_search_credential(s))


def ensure_index(index_client: Any, index: Any) -> Any:
    """Create or update the index (idempotent)."""
    return index_client.create_or_update_index(index)


def load_path(path: Path) -> list[IngestDocument]:
    """Every ``.md``/``.txt`` file under ``path`` (or the file itself) as a document."""
    files = (
        [path]
        if path.is_file()
        else sorted(p for p in path.rglob("*") if p.suffix.lower() in TEXT_SUFFIXES)
    )
    docs: list[IngestDocument] = []
    for file in files:
        if file.suffix.lower() not in TEXT_SUFFIXES:
            continue
        docs.append(IngestDocument(source=file.as_posix(), text=file.read_text(encoding="utf-8")))
    return docs


def _batches(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


async def ingest_documents(
    documents: Iterable[IngestDocument],
    *,
    embeddings: Embeddings,
    search_client: Any,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    batch_size: int = 64,
) -> IngestReport:
    """Chunk, embed and upload. Returns counts only."""
    log = get_logger("app.ai.ingest")
    report = IngestReport()
    records: list[dict[str, Any]] = []
    for doc in documents:
        report.documents += 1
        for i, piece in enumerate(chunk_text(doc.text, chunk_size, overlap)):
            records.append(
                {
                    ID_FIELD: chunk_id(doc.source, i),
                    CONTENT_FIELD: piece,
                    SOURCE_FIELD: doc.source,
                    CHUNK_INDEX_FIELD: i,
                }
            )
    report.chunks = len(records)
    for batch in _batches(records, batch_size):
        vectors = await embeddings.aembed_documents([r[CONTENT_FIELD] for r in batch])
        payload = [{**r, VECTOR_FIELD: v} for r, v in zip(batch, vectors, strict=True)]
        results = await asyncio.to_thread(search_client.upload_documents, documents=payload)
        ok = sum(1 for r in results if getattr(r, "succeeded", False))
        report.uploaded += ok
        report.failed += len(payload) - ok
        log.info("ingest batch uploaded", uploaded=ok, failed=len(payload) - ok)
    log.info(
        "ingest complete",
        documents=report.documents,
        chunks=report.chunks,
        uploaded=report.uploaded,
        failed=report.failed,
    )
    return report


async def run(argv: Sequence[str] | None = None) -> IngestReport:
    parser = argparse.ArgumentParser(prog="python -m app.ai.ingest", description=__doc__)
    parser.add_argument("path", type=Path, help="a .md/.txt file or a directory to ingest")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args(argv)

    from app.ai.client import get_embeddings

    settings = get_ai_settings()
    settings.require_search()
    settings.require_embeddings()
    index = build_index(settings.search_index or "", settings.embedding_dimensions)
    ensure_index(build_index_client(settings), index)
    return await ingest_documents(
        load_path(args.path),
        embeddings=get_embeddings(),
        search_client=build_search_client(settings),
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        batch_size=args.batch_size,
    )


def main() -> None:
    configure_logging()
    report = asyncio.run(run(sys.argv[1:]))
    print(
        f"documents={report.documents} chunks={report.chunks} "
        f"uploaded={report.uploaded} failed={report.failed}"
    )
    if report.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
