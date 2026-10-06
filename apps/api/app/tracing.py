"""Request-scoped distributed tracing primitives (shared contract).

Trace id layout (32 lowercase hex chars total):
    origin(4 hex) + env(1 hex) + random(27 hex)

This service:
    origin = "0c70"  (the api service)

env hex mapping (from APP_ENV):
    local=0, dev=1, staging=2, prod=3, sandbox=4
    unknown/missing APP_ENV -> local (0)

Canonical header: "x-trace-id" (lowercase).
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Mapping
from contextvars import ContextVar

import httpx
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.metrics import record_hop_duration, record_server_duration, resolve_target, status_class

# --- contract constants -----------------------------------------------------

ORIGIN = "0c70"
TRACE_HEADER = "x-trace-id"
_TRACE_RE = re.compile(r"^[0-9a-f]{32}$")

_ENV_HEX: dict[str, str] = {
    "local": "0",
    "dev": "1",
    "staging": "2",
    "prod": "3",
    "sandbox": "4",
}

# --- request-scoped storage -------------------------------------------------

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def env_hex(app_env: str | None) -> str:
    """Map an APP_ENV string to its single hex char; unknown -> local (0)."""
    if not app_env:
        return _ENV_HEX["local"]
    return _ENV_HEX.get(app_env.strip().lower(), _ENV_HEX["local"])


def generate_trace_id() -> str:
    """Generate a fresh 32-hex trace id for this service's origin/env."""
    env = env_hex(get_settings().app_env)
    return f"{ORIGIN}{env}{secrets.token_hex(14)[:27]}"


def is_valid_trace_id(s: str | None) -> bool:
    """Validate a candidate trace id against ^[0-9a-f]{32}$."""
    return bool(s) and bool(_TRACE_RE.match(s))


def set_trace_id(trace_id: str) -> None:
    """Set the trace id for the current request scope."""
    _trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    """Read the trace id bound to the current request scope (or None)."""
    return _trace_id_var.get()


def _header_from_scope(scope: Scope) -> str | None:
    """Extract the inbound x-trace-id header value from a raw ASGI scope."""
    for key, value in scope.get("headers", []):
        if key == TRACE_HEADER.encode("latin-1"):
            return value.decode("latin-1")
    return None


class TraceMiddleware:
    """Pure-ASGI middleware that manages the x-trace-id lifecycle.

    On each request it:
      1. Reads the inbound ``x-trace-id`` header.
      2. Adopts it if valid, otherwise generates a fresh id (api origin).
      3. Binds it to the request-scoped contextvar.
      4. Echoes it back on the response ``x-trace-id`` header.
      5. Records the request-duration metric by route class and status class
         (Phase 3 — the route PATTERN, e.g. "/v1/things/{id}", stays bounded;
         unrouted requests collapse to "unmatched").
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = _header_from_scope(scope)
        trace_id = inbound if is_valid_trace_id(inbound) else generate_trace_id()
        token = _trace_id_var.set(trace_id)
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 0)
                headers = list(message.get("headers", []))
                name = TRACE_HEADER.encode("latin-1")
                # Replace any existing value, then set ours.
                headers = [(k, v) for (k, v) in headers if k != name]
                headers.append((name, trace_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _trace_id_var.reset(token)
            # The router stamps scope["route"] once a route matched; its .path
            # is the bounded pattern. An unhandled exception (no response
            # started) surfaces as the server's 500.
            route_class = getattr(scope.get("route"), "path", None) or "unmatched"
            record_server_duration(
                route_class=route_class,
                method=scope.get("method", "unknown"),
                status_code=status_holder["status"] or 500,
                duration_ms=(time.perf_counter() - start) * 1000,
            )


def forward_headers(headers: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a headers dict with the current x-trace-id injected.

    Used to propagate the trace id on outbound calls. Existing headers are
    preserved; the trace header is only added when a trace id is in scope.
    """
    out: dict[str, str] = dict(headers or {})
    trace_id = get_trace_id()
    if trace_id:
        out[TRACE_HEADER] = trace_id
    return out


_HOP_START_EXTENSION = "traced_client_hop_start"


# Both hooks MUST be async even though they await nothing: httpx.AsyncClient
# calls `await hook(...)` unconditionally — a sync callable would crash it.
async def _hop_request_hook(request: httpx.Request) -> None:
    request.extensions[_HOP_START_EXTENSION] = time.perf_counter()


async def _hop_response_hook(response: httpx.Response) -> None:
    start = response.request.extensions.get(_HOP_START_EXTENSION)
    if isinstance(start, float):
        record_hop_duration(
            target=resolve_target(str(response.request.url)),
            outcome=status_class(response.status_code),
            duration_ms=(time.perf_counter() - start) * 1000,
        )


# Explicit default timeout for every outbound hop (rule 50 → External HTTP:
# never an unbounded wait). Callers may pass their own ``timeout=``.
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 10.0


def traced_client(**kwargs: object) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient that forwards the current x-trace-id.

    The ONLY sanctioned outbound HTTP client in this service (bare httpx is a
    review-blocking violation, see .claude/rules/35-fastapi.md). Provided for
    future downstream calls (the baseline has none). The trace header is
    merged into any caller-supplied default headers; W3C ``traceparent`` and
    the AppDependencies span come from the httpx instrumentation registered at
    init. Event hooks record the chain-hop duration metric (responses only —
    httpx has no error hook; the dependency span still captures failures).
    Every request is bounded by an explicit timeout
    (``DEFAULT_UPSTREAM_TIMEOUT_SECONDS`` unless the caller passes ``timeout=``).
    """
    kwargs.setdefault("timeout", httpx.Timeout(DEFAULT_UPSTREAM_TIMEOUT_SECONDS))
    base_headers = kwargs.pop("headers", None)
    merged = forward_headers(base_headers if isinstance(base_headers, Mapping) else None)
    hooks = kwargs.pop("event_hooks", None)
    merged_hooks: dict[str, list[object]] = (
        {str(k): list(v) for k, v in hooks.items()} if isinstance(hooks, Mapping) else {}
    )
    merged_hooks.setdefault("request", []).append(_hop_request_hook)
    merged_hooks.setdefault("response", []).append(_hop_response_hook)
    return httpx.AsyncClient(headers=merged, event_hooks=merged_hooks, **kwargs)  # type: ignore[arg-type]
