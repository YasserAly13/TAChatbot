"""The OpenAPI export is deterministic, covers the operational routes, and the committed copy
in docs/reference/openapi.json is current (the contract the web layer types against)."""

from __future__ import annotations

import json
from pathlib import Path

from app.openapi_export import DEFAULT_OUTPUT, export_openapi, render_openapi


def test_render_is_deterministic_and_includes_operational_routes() -> None:
    first, second = render_openapi(), render_openapi()
    assert first == second
    doc = json.loads(first)
    assert doc["info"]["title"].endswith("api")
    assert {"/ping", "/health", "/info"} <= set(doc["paths"])
    assert first.endswith("\n")


def test_export_writes_the_file(tmp_path: Path) -> None:
    out = export_openapi(tmp_path / "nested" / "openapi.json")
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8"))["openapi"].startswith("3.")


def test_committed_contract_is_current() -> None:
    """`make openapi` must be run after any change to the HTTP surface (rule 14)."""
    assert DEFAULT_OUTPUT.is_file(), "docs/reference/openapi.json is missing — run `make openapi`"
    # Semantic comparison: the committed file is prettier-formatted by `make openapi`, so
    # whitespace may differ from the raw render; the document must not.
    committed = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    assert committed == json.loads(render_openapi()), (
        "docs/reference/openapi.json is stale — run `make openapi`"
    )
