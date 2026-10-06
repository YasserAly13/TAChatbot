"""The api error contract: every non-2xx response body is ``{"error": <code>, "trace_id": <id>}``.

Why a contract: the BFF (apps/web) and the UI type against it, and the trace id in the body
lets a developer paste one id into Log Analytics. What it never does: echo exception messages,
validation details or stack traces to the client (rule 50) — the structured log line carries
the exception *kind* and location, the client gets a bounded ``snake_case`` code.

Pieces:

* ``ErrorBody`` — the Pydantic model, also used to document ``/v1`` responses in OpenAPI.
* ``ApiError`` (+ ``NotFound``, ``Conflict``, ``AIUnavailable``) — raise these from routes and
  repositories; ``install_error_handlers`` turns them into the contract.
* Handlers for Starlette's ``HTTPException`` (a ``snake_case`` ``detail`` becomes the code, any
  other detail maps to a default per status), FastAPI's ``RequestValidationError`` (``422
  validation_error`` — the offending fields are logged, not returned) and ``AINotConfigured``
  (``503 ai_unavailable``).
* ``UnhandledErrorMiddleware`` — a pure-ASGI catch-all for anything the handlers did not see.
  It runs **inside** ``TraceMiddleware`` so the 500 still carries the request's trace id in the
  body and the echoed header. Once a response has started (streaming), nothing can be rewritten;
  the exception is re-raised so the connection drops instead of a half-body pretending to be ok.

Codes are stable identifiers, not sentences. Add a new one by subclassing ``ApiError``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.ai.config import AINotConfigured
from app.logging_config import get_logger
from app.tracing import generate_trace_id, get_trace_id

_log = get_logger("app.errors")

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# Default codes for HTTPExceptions whose ``detail`` is prose (FastAPI's own 404/405, etc.).
_DEFAULT_CODES: Mapping[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


class ErrorBody(BaseModel):
    """The one error shape every api response uses."""

    error: str = Field(description="Stable snake_case code, e.g. not_found, validation_error.")
    trace_id: str = Field(
        description="The request's trace id — the same value as the x-trace-id header."
    )


class ApiError(Exception):
    """Raise from routes/repositories; becomes ``{error, trace_id}`` with ``status_code``."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, code: str | None = None, *, status_code: int | None = None) -> None:
        if code is not None:
            if not _CODE_RE.match(code):
                raise ValueError(f"error code must be snake_case: {code!r}")
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.code)


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


class AIUnavailable(ApiError):
    """The model/search backend is not configured or did not answer (bounded; no upstream text)."""

    status_code = 503
    code = "ai_unavailable"


def current_trace_id() -> str:
    """The request's trace id, with a defensive fallback for handlers that run outside a scope."""
    return get_trace_id() or generate_trace_id()


def code_for_status(status_code: int) -> str:
    return _DEFAULT_CODES.get(status_code, "http_error")


def error_response(
    code: str, status_code: int, *, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    """Build the contract response (handlers, and streaming routes before the stream starts)."""
    body = ErrorBody(error=code, trace_id=current_trace_id())
    return JSONResponse(
        status_code=status_code, content=body.model_dump(), headers=dict(headers or {})
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the exception handlers on the app (called once from ``create_app``)."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        if exc.status_code >= 500:
            _log.error("api error", error=exc.code, status=exc.status_code)
        return error_response(exc.code, exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else ""
        code = detail if _CODE_RE.match(detail) else code_for_status(exc.status_code)
        if exc.status_code >= 500:
            _log.error("http error", error=code, status=exc.status_code)
        # Keep protocol headers such as Allow (405) or WWW-Authenticate (401).
        return error_response(code, exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations are safe and useful in the log; values are not returned to the client.
        locations = sorted({".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()})
        _log.info("request validation failed", fields=locations, count=len(locations))
        return error_response("validation_error", 422)

    @app.exception_handler(AINotConfigured)
    async def _ai_not_configured(_: Request, exc: AINotConfigured) -> JSONResponse:
        _log.error("ai not configured", kind=type(exc).__name__)
        return error_response(AIUnavailable.code, AIUnavailable.status_code)


class UnhandledErrorMiddleware:
    """Last line of defence: an exception no handler caught becomes ``500 internal_error``.

    Pure ASGI so it sits directly inside ``TraceMiddleware``: the trace id is already bound,
    and the outer middleware still stamps the ``x-trace-id`` header on the 500 we send.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 — the whole point is to catch everything
            tb = exc.__traceback__
            while tb is not None and tb.tb_next is not None:
                tb = tb.tb_next
            where = (
                f"{tb.tb_frame.f_code.co_filename}:{tb.tb_frame.f_code.co_name}:{tb.tb_lineno}"
                if tb is not None
                else "unknown"
            )
            # Kind + location only — never the message (it may contain user or secret data).
            _log.error("unhandled exception", kind=type(exc).__name__, where=where)
            if started:
                raise
            response = error_response("internal_error", 500)
            await response(scope, receive, send)
