"""Unit tests for the request-scoped tracing primitives."""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.tracing as tracing_mod
from app.tracing import ORIGIN, TraceMiddleware, env_hex, generate_trace_id, is_valid_trace_id

TRACE_RE = re.compile(r"^[0-9a-f]{32}$")


def test_env_hex_mapping() -> None:
    assert env_hex("local") == "0"
    assert env_hex("dev") == "1"
    assert env_hex("staging") == "2"
    assert env_hex("prod") == "3"
    assert env_hex("sandbox") == "4"


def test_env_hex_unknown_or_missing_is_local() -> None:
    assert env_hex("nope") == "0"
    assert env_hex(None) == "0"


def test_generate_trace_id_shape() -> None:
    tid = generate_trace_id()
    assert TRACE_RE.match(tid)
    assert len(tid) == 32
    assert tid.startswith(ORIGIN)  # api origin 0c70


def test_generate_trace_id_is_unique() -> None:
    assert generate_trace_id() != generate_trace_id()


def test_is_valid_trace_id() -> None:
    assert is_valid_trace_id("0c70" + "0" + "a" * 27)
    assert not is_valid_trace_id("nope")
    assert not is_valid_trace_id("0C70" + "0" + "a" * 27)  # uppercase rejected
    assert not is_valid_trace_id("0c70" + "0" + "a" * 26)  # wrong length
    assert not is_valid_trace_id(None)
    assert not is_valid_trace_id("")


# --- request-duration metric (Phase 3) ---------------------------------------


@pytest.fixture()
def duration_samples(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> None:
        samples.append(kwargs)

    monkeypatch.setattr(tracing_mod, "record_server_duration", record)
    return samples


def _mini_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("handler boom")

    return app


def test_middleware_records_route_pattern_not_raw_path(
    duration_samples: list[dict[str, Any]],
) -> None:
    client = TestClient(_mini_app())
    res = client.get("/items/42")
    assert res.status_code == 200
    assert len(duration_samples) == 1
    sample = duration_samples[0]
    # The bounded PATTERN, never the parameterized concrete path.
    assert sample["route_class"] == "/items/{item_id}"
    assert sample["method"] == "GET"
    assert sample["status_code"] == 200
    assert sample["duration_ms"] >= 0


def test_middleware_records_unmatched_for_404(duration_samples: list[dict[str, Any]]) -> None:
    client = TestClient(_mini_app())
    res = client.get("/no/such/route")
    assert res.status_code == 404
    assert duration_samples[0]["route_class"] == "unmatched"
    assert duration_samples[0]["status_code"] == 404


def test_middleware_records_500_when_handler_raises(
    duration_samples: list[dict[str, Any]],
) -> None:
    client = TestClient(_mini_app(), raise_server_exceptions=False)
    res = client.get("/boom")
    assert res.status_code == 500
    assert duration_samples[0]["status_code"] == 500
    assert duration_samples[0]["route_class"] == "/boom"


# --- traced_client hop metric (Phase 3) ---------------------------------------


def test_traced_client_records_hop_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    hops: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> None:
        hops.append(kwargs)

    monkeypatch.setattr(tracing_mod, "record_hop_duration", record)
    monkeypatch.setenv("API_BASE_URL", "http://upstream:8000")

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    async def run() -> None:
        async with tracing_mod.traced_client(transport=httpx.MockTransport(respond)) as client:
            await client.get("http://upstream:8000/ping")

    import asyncio

    asyncio.run(run())

    assert len(hops) == 1
    assert hops[0]["target"] == "api"
    assert hops[0]["outcome"] == "2xx"
    assert hops[0]["duration_ms"] >= 0


def test_traced_client_preserves_caller_event_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def caller_hook(request: httpx.Request) -> None:
        seen.append(str(request.url))

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    async def run() -> None:
        async with tracing_mod.traced_client(
            transport=httpx.MockTransport(respond),
            event_hooks={"request": [caller_hook]},
        ) as client:
            await client.get("http://anywhere/x")

    import asyncio

    asyncio.run(run())

    assert seen == ["http://anywhere/x"]


# --- traced_client timeout (rule 50: never an unbounded wait) ------------------


def test_traced_client_sets_an_explicit_default_timeout() -> None:
    client = tracing_mod.traced_client()
    try:
        assert client.timeout == httpx.Timeout(tracing_mod.DEFAULT_UPSTREAM_TIMEOUT_SECONDS)
    finally:
        import asyncio

        asyncio.run(client.aclose())


def test_traced_client_honors_caller_timeout() -> None:
    client = tracing_mod.traced_client(timeout=httpx.Timeout(2.5))
    try:
        assert client.timeout == httpx.Timeout(2.5)
    finally:
        import asyncio

        asyncio.run(client.aclose())
