"""HTTP routes: /ping, /health and /info.

All endpoints return the request-scoped trace id (set by TraceMiddleware).
The x-trace-id response header is added by the middleware, not here.
"""

from __future__ import annotations

import os
import platform
import socket
import time

from fastapi import APIRouter

from app.config import SERVICE_NAME, get_settings, get_version
from app.logging_config import get_logger
from app.observability import get_observability_state
from app.tracing import generate_trace_id, get_trace_id

router = APIRouter()
_log = get_logger("app.routes")

# Process start, captured at import (≈ service boot) so /info can report uptime.
_STARTED = time.monotonic()
_VERSION = get_version()


def _current_trace_id() -> str:
    """Trace id from request scope, with a defensive fallback."""
    return get_trace_id() or generate_trace_id()


@router.get("/ping")
async def ping() -> dict[str, str]:
    """Liveness greeting endpoint."""
    trace_id = _current_trace_id()
    _log.info("ping", path="/ping")
    return {
        "service": SERVICE_NAME,
        "message": "hello from the AI Accelerator api service",
        "trace_id": trace_id,
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Health endpoint reporting observability state."""
    trace_id = _current_trace_id()
    obs = get_observability_state()
    _log.info("health", path="/health", observability_enabled=obs["enabled"])
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "trace_id": trace_id,
        "observability": "enabled" if obs["enabled"] else "disabled",
        "reason": obs["reason"],
    }


@router.get("/info")
async def info() -> dict[str, object]:
    """Consolidated status + version + runtime report for this service.

    Extends the /health shape with the build version and runtime/system
    metadata. Reachable only via the BFF (web) on the internal network.
    """
    trace_id = _current_trace_id()
    obs = get_observability_state()
    _log.info("info", path="/info")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": _VERSION,
        "env": get_settings().app_env,
        "uptime_seconds": round(time.monotonic() - _STARTED, 3),
        "runtime": {"name": "python", "version": platform.python_version()},
        "system": {
            "platform": platform.system(),
            "arch": platform.machine(),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
        },
        "observability": "enabled" if obs["enabled"] else "disabled",
        "reason": obs["reason"],
        "trace_id": trace_id,
    }
