"""HTTP tests for /ping and /health via Starlette's TestClient.

Exercises the trace contract (adopt valid inbound id / regenerate invalid /
echo the header) and degraded observability (no connection string in tests).
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ORIGIN_RE = re.compile(r"^0c70[0-9a-f]{28}$")


def test_ping_mints_origin_trace_id_and_echoes_header() -> None:
    res = client.get("/ping")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "api"
    assert isinstance(body["message"], str)
    assert ORIGIN_RE.match(body["trace_id"])
    assert res.headers["x-trace-id"] == body["trace_id"]


def test_ping_adopts_valid_inbound_trace_id() -> None:
    tid = "0eb00" + "a" * 27
    res = client.get("/ping", headers={"x-trace-id": tid})
    assert res.json()["trace_id"] == tid
    assert res.headers["x-trace-id"] == tid


def test_ping_regenerates_invalid_inbound_trace_id() -> None:
    res = client.get("/ping", headers={"x-trace-id": "not-a-valid-id"})
    assert ORIGIN_RE.match(res.json()["trace_id"])


def test_health_reports_degraded_observability_without_connection_string() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert body["observability"] == "disabled"
    assert isinstance(body["reason"], str)


def test_info_reports_status_version_runtime_and_trace_id() -> None:
    res = client.get("/info")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert isinstance(body["version"], str)
    assert body["runtime"]["name"] == "python"
    assert isinstance(body["uptime_seconds"], (int, float))
    assert "hostname" in body["system"]
    # No connection string in tests -> degraded mode, never throws.
    assert body["observability"] == "disabled"
    assert ORIGIN_RE.match(body["trace_id"])
    assert res.headers["x-trace-id"] == body["trace_id"]


def test_info_adopts_valid_inbound_trace_id() -> None:
    tid = "0eb00" + "a" * 27
    res = client.get("/info", headers={"x-trace-id": tid})
    assert res.json()["trace_id"] == tid
    assert res.headers["x-trace-id"] == tid
