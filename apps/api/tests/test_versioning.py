"""Enforces the mandatory API-versioning policy (ADR-0001 / rule 05) for the api service.

- operational endpoints (/ping, /health, /info) stay unversioned and are NOT
  reachable under /v1 (guards the health-probe paths);
- the /v1 router prefix actually produces /v1/<path> for business routers.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.routers import API_V1_PREFIX, v1_router

client = TestClient(app)


def test_v1_prefix_constant() -> None:
    assert API_V1_PREFIX == "/v1"
    assert v1_router.prefix == "/v1"


def test_operational_endpoints_are_unversioned() -> None:
    for path in ("/ping", "/health", "/info"):
        assert client.get(path).status_code == 200


def test_operational_endpoints_are_not_exposed_under_v1() -> None:
    for path in ("/v1/ping", "/v1/health", "/v1/info"):
        assert client.get(path).status_code == 404


def test_business_router_is_served_under_v1() -> None:
    # A feature router attached to a /v1-prefixed router must resolve at /v1/<path>.
    feature = APIRouter(prefix="/widgets")

    @feature.get("")
    async def _list() -> dict[str, bool]:
        return {"ok": True}

    versioned = APIRouter(prefix=API_V1_PREFIX)
    versioned.include_router(feature)
    probe = FastAPI()
    probe.include_router(versioned)
    probe_client = TestClient(probe)

    assert probe_client.get("/v1/widgets").status_code == 200
    assert probe_client.get("/widgets").status_code == 404
