"""Telemetry for model and retrieval calls (ADR-0009; rule 60 → *Metrics & events*).

What is recorded — and what is NOT:

- A span per model call with the OpenTelemetry GenAI semantic-convention attributes we can
  fill without content capture: ``gen_ai.system``, ``gen_ai.operation.name``,
  ``gen_ai.request.model`` (the deployment), ``gen_ai.usage.input_tokens`` /
  ``gen_ai.usage.output_tokens``, plus our ``trace_id``.
- Metrics (bounded attributes only — a deployment name is a short, fixed set):
  ``team-assistant.ai.model.duration`` (ms, by deployment/outcome),
  ``team-assistant.ai.model.tokens`` (by deployment/token_type),
  ``team-assistant.ai.model.failures`` (by deployment/error_kind),
  ``team-assistant.ai.retrieval.duration`` (ms, by outcome).
- One custom event per model call (``ai.model_call``) with the same bounded attributes.
- **Never** the prompt, the completion, retrieved text, or user identifiers — in spans, logs,
  metrics or events. PII in chat history is a data-classification concern for the project;
  telemetry stays content-free by construction.

All helpers are best-effort: telemetry can never break a request.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace
from opentelemetry.metrics import Counter, Histogram

from app.events import track_event
from app.logging_config import get_logger
from app.metrics import get_meter
from app.tracing import get_trace_id

GEN_AI_SYSTEM = "azure_openai"
_TRACER_NAME = "team-assistant.ai"

_model_duration: Histogram | None = None
_model_tokens: Counter | None = None
_model_failures: Counter | None = None
_retrieval_duration: Histogram | None = None


def _instruments() -> tuple[Histogram, Counter, Counter, Histogram]:
    global _model_duration, _model_tokens, _model_failures, _retrieval_duration
    meter = get_meter("ai")
    if _model_duration is None:
        _model_duration = meter.create_histogram(
            "team-assistant.ai.model.duration", unit="ms", description="Model call duration"
        )
    if _model_tokens is None:
        _model_tokens = meter.create_counter(
            "team-assistant.ai.model.tokens", unit="1", description="Tokens by type"
        )
    if _model_failures is None:
        _model_failures = meter.create_counter(
            "team-assistant.ai.model.failures", unit="1", description="Failed model calls"
        )
    if _retrieval_duration is None:
        _retrieval_duration = meter.create_histogram(
            "team-assistant.ai.retrieval.duration", unit="ms", description="Retrieval duration"
        )
    return _model_duration, _model_tokens, _model_failures, _retrieval_duration


def error_kind(exc: BaseException) -> str:
    """Bounded classification of a failure (never the message — it may echo content)."""
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "ratelimit" in name or "429" in name:
        return "rate_limited"
    if "auth" in name or "permission" in name or "401" in name or "403" in name:
        return "auth"
    if "connection" in name or "network" in name:
        return "network"
    return "error"


def extract_usage(message: Any) -> tuple[int | None, int | None]:
    """(input_tokens, output_tokens) from a LangChain ``AIMessage`` — ``None`` when not reported."""
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None, None
    return usage.get("input_tokens"), usage.get("output_tokens")


@dataclass
class ModelCallRecorder:
    """Handed to the caller inside ``model_call_span`` to report usage/outcome."""

    deployment: str
    operation: str
    started: float = field(default_factory=time.perf_counter)
    input_tokens: int | None = None
    output_tokens: int | None = None

    def set_usage(self, message: Any) -> None:
        self.input_tokens, self.output_tokens = extract_usage(message)


def _finish(recorder: ModelCallRecorder, outcome: str, error: str | None, span: Any) -> None:
    duration_ms = (time.perf_counter() - recorder.started) * 1000
    attrs = {"deployment": recorder.deployment, "outcome": outcome}
    try:
        duration, tokens, failures, _ = _instruments()
        duration.record(duration_ms, attrs)
        if recorder.input_tokens is not None:
            tokens.add(recorder.input_tokens, {**attrs, "token_type": "input"})
        if recorder.output_tokens is not None:
            tokens.add(recorder.output_tokens, {**attrs, "token_type": "output"})
        if error is not None:
            failures.add(1, {"deployment": recorder.deployment, "error_kind": error})
    except Exception:  # noqa: BLE001 - metrics must never break the request path
        pass
    try:
        if span is not None:
            if recorder.input_tokens is not None:
                span.set_attribute("gen_ai.usage.input_tokens", recorder.input_tokens)
            if recorder.output_tokens is not None:
                span.set_attribute("gen_ai.usage.output_tokens", recorder.output_tokens)
            span.set_attribute("ai.outcome", outcome)
            if error is not None:
                span.set_attribute("ai.error_kind", error)
    except Exception:  # noqa: BLE001
        pass
    event_attrs: dict[str, str | int | float | bool] = {
        "deployment": recorder.deployment,
        "operation": recorder.operation,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 1),
    }
    if recorder.input_tokens is not None:
        event_attrs["input_tokens"] = recorder.input_tokens
    if recorder.output_tokens is not None:
        event_attrs["output_tokens"] = recorder.output_tokens
    if error is not None:
        event_attrs["error_kind"] = error
    track_event("ai.model_call", event_attrs)
    get_logger("app.ai").info("model call", **event_attrs)


@contextmanager
def model_call_span(deployment: str, operation: str = "chat") -> Iterator[ModelCallRecorder]:
    """Wrap one model call: span + metrics + event. Re-raises the caller's exception.

    Usage::

        with model_call_span(settings.chat_deployment) as call:
            response = await model.ainvoke(messages)
            call.set_usage(response)
    """
    recorder = ModelCallRecorder(deployment=deployment, operation=operation)
    tracer = trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(f"gen_ai.{operation}") as span:
        try:
            span.set_attribute("gen_ai.system", GEN_AI_SYSTEM)
            span.set_attribute("gen_ai.operation.name", operation)
            span.set_attribute("gen_ai.request.model", deployment)
            trace_id = get_trace_id()
            if trace_id:
                span.set_attribute("trace_id", trace_id)
        except Exception:  # noqa: BLE001
            pass
        try:
            yield recorder
        except BaseException as exc:
            _finish(recorder, "error", error_kind(exc), span)
            raise
        _finish(recorder, "ok", None, span)


def record_retrieval(duration_ms: float, outcome: str, hits: int | None = None) -> None:
    """One retrieval sample (bounded ``outcome``; ``hits`` goes to the log line only)."""
    try:
        _, _, _, retrieval = _instruments()
        retrieval.record(duration_ms, {"outcome": outcome})
    except Exception:  # noqa: BLE001
        pass
    get_logger("app.ai").info(
        "retrieval", outcome=outcome, duration_ms=round(duration_ms, 1), hits=hits
    )


def _reset_for_tests() -> None:
    """TEST-ONLY: drop cached instruments."""
    global _model_duration, _model_tokens, _model_failures, _retrieval_duration
    _model_duration = _model_tokens = _model_failures = _retrieval_duration = None
