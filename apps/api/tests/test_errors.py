"""The api error contract (app/errors.py): every non-2xx body is {error, trace_id}, details are
never echoed, the trace id matches the header, and a 500 still carries both."""

from __future__ import annotations

import re

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.ai.config import AINotConfigured
from app.errors import (
    ApiError,
    Conflict,
    NotFound,
    UnhandledErrorMiddleware,
    code_for_status,
    install_error_handlers,
)
from app.main import app as real_app
from app.tracing import TraceMiddleware

TRACE_RE = re.compile(r"^[0-9a-f]{32}$")
INBOUND = "0eb01" + "b" * 27


def _mini_app() -> FastAPI:
    """A tiny app with the production error plumbing and routes that fail in every way."""
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(TraceMiddleware)  # outermost, as in create_app
    router = APIRouter(prefix="/v1")

    @router.get("/missing")
    async def missing() -> dict:
        raise NotFound()

    @router.get("/busy")
    async def busy() -> dict:
        raise Conflict("ingest_running")

    @router.get("/typed")
    async def typed(limit: int) -> dict:
        return {"limit": limit}

    @router.get("/http")
    async def http() -> dict:
        raise HTTPException(status_code=418, detail="I'm a teapot — with a message")

    @router.get("/http-coded")
    async def http_coded() -> dict:
        raise HTTPException(status_code=403, detail="read_only")

    @router.get("/ai")
    async def ai() -> dict:
        raise AINotConfigured("AZURE_AI_ENDPOINT is not set — secret value would be here")

    @router.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("database password is hunter2")

    app.include_router(router)
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_mini_app(), raise_server_exceptions=False)


def _assert_contract(res, status: int, code: str) -> None:
    assert res.status_code == status
    body = res.json()
    assert set(body) == {"error", "trace_id"}, body
    assert body["error"] == code
    assert TRACE_RE.match(body["trace_id"])
    assert res.headers["x-trace-id"] == body["trace_id"]


def test_real_app_unknown_route_is_not_found_with_trace_id() -> None:
    res = TestClient(real_app).get("/v1/nope")
    _assert_contract(res, 404, "not_found")
    assert res.json()["trace_id"].startswith("0c70")


def test_real_app_adopts_inbound_trace_id_on_errors() -> None:
    res = TestClient(real_app).get("/v1/nope", headers={"x-trace-id": INBOUND})
    _assert_contract(res, 404, "not_found")
    assert res.json()["trace_id"] == INBOUND


def test_method_not_allowed_keeps_allow_header() -> None:
    res = TestClient(real_app).post("/ping")
    _assert_contract(res, 405, "method_not_allowed")
    assert "GET" in res.headers["allow"]


def test_operational_routes_unchanged() -> None:
    client = TestClient(real_app)
    assert client.get("/ping").status_code == 200
    assert client.get("/health").status_code == 200


def test_api_error_subclasses(client: TestClient) -> None:
    _assert_contract(client.get("/v1/missing"), 404, "not_found")
    _assert_contract(client.get("/v1/busy"), 409, "ingest_running")


def test_validation_error_does_not_echo_details(client: TestClient) -> None:
    res = client.get("/v1/typed", params={"limit": "not-a-number"})
    _assert_contract(res, 422, "validation_error")
    assert "not-a-number" not in res.text
    assert "limit" not in res.json().values()


def test_http_exception_prose_detail_maps_to_default_code(client: TestClient) -> None:
    res = client.get("/v1/http")
    _assert_contract(res, 418, "http_error")
    assert "teapot" not in res.text


def test_http_exception_snake_case_detail_becomes_the_code(client: TestClient) -> None:
    _assert_contract(client.get("/v1/http-coded"), 403, "read_only")


def test_ai_not_configured_is_503_without_the_message(client: TestClient) -> None:
    res = client.get("/v1/ai")
    _assert_contract(res, 503, "ai_unavailable")
    assert "AZURE_AI_ENDPOINT" not in res.text


def test_unhandled_exception_is_500_with_trace_id_and_no_message(client: TestClient) -> None:
    res = client.get("/v1/boom", headers={"x-trace-id": INBOUND})
    _assert_contract(res, 500, "internal_error")
    assert res.json()["trace_id"] == INBOUND
    assert "hunter2" not in res.text


def test_api_error_rejects_non_snake_case_codes() -> None:
    with pytest.raises(ValueError):
        ApiError("Not A Code")
    assert ApiError("custom_code", status_code=400).status_code == 400


def test_code_for_status_defaults() -> None:
    assert code_for_status(404) == "not_found"
    assert code_for_status(422) == "validation_error"
    assert code_for_status(418) == "http_error"
