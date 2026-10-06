"""Streamed answers as Server-Sent Events (ADR-0009).

Wire format (one ``event:`` + one JSON ``data:`` line per event, blank-line terminated):

    event: sources   data: {"sources": [{"title": "A", "path": "docs/a.md"}], "count": 3}
                                                                    — after retrieval
    event: token     data: {"text": "partial "}                     — per model token chunk
    event: done      data: {"sources": [...], "input_tokens": 12, "output_tokens": 40}
    event: error     data: {"error_kind": "timeout"}                — then the stream ends

``sources`` lists each cited document once, ``{title, path}`` (B8 #7); ``count`` is the number of
retrieved chunks.

Use from a ``/v1`` route::

    @router.post("/chat/stream")
    async def chat_stream(body: ChatIn) -> StreamingResponse:
        graph = build_graph()
        return sse_response(stream_answer(graph, body.question))

The BFF forwards it with the streaming pass-through helper (``apps/web/src/lib/stream.ts``),
not ``fetchUpstream`` (which forces a JSON accept header and a 10 s timeout).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, AnyMessage, HumanMessage

from app.ai.graph import GraphState, Source, _message_text, unique_sources
from app.ai.telemetry import error_kind, extract_usage

SSE_MEDIA_TYPE = "text/event-stream"


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_answer(
    graph: Any,
    question: str,
    *,
    history: list[AnyMessage] | None = None,
    config: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Run the graph and yield SSE frames: ``sources`` → ``token``* → ``done`` (or ``error``)."""
    inputs: GraphState = {
        "messages": [*(history or []), HumanMessage(content=question)],
        "context": [],
    }
    sources: list[Source] = []
    input_tokens: int | None = None
    output_tokens: int | None = None
    try:
        async for mode, payload in graph.astream(
            inputs, config, stream_mode=["updates", "messages"]
        ):
            if mode == "updates":
                for node, update in (payload or {}).items():
                    if node == "retrieve":
                        context = (update or {}).get("context", []) or []
                        sources = unique_sources(context)
                        yield sse("sources", {"sources": sources, "count": len(context)})
                    elif node == "answer":
                        for message in (update or {}).get("messages", []) or []:
                            i, o = extract_usage(message)
                            input_tokens = i if i is not None else input_tokens
                            output_tokens = o if o is not None else output_tokens
            elif mode == "messages":
                chunk, metadata = payload
                if (
                    isinstance(chunk, AIMessageChunk)
                    and (metadata or {}).get("langgraph_node") == "answer"
                    and not getattr(chunk, "tool_call_chunks", None)
                ):
                    text = _message_text(chunk)
                    if text:
                        yield sse("token", {"text": text})
    except Exception as exc:  # noqa: BLE001 - the frame carries a bounded kind, never the message
        yield sse("error", {"error_kind": error_kind(exc)})
        return
    yield sse(
        "done",
        {"sources": sources, "input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def sse_response(frames: AsyncIterator[str]) -> StreamingResponse:
    """A FastAPI response that streams SSE frames without proxy buffering."""
    return StreamingResponse(
        frames,
        media_type=SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
