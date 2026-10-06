"""The LangGraph skeleton (ADR-0009): ``retrieve → answer`` (+ an optional tool loop).

Shape a project copies for its own graphs:

- **Typed state** (``GraphState``): the message history (``add_messages`` reducer) and the
  retrieved context.
- **Nodes are small async functions** that do one I/O each, with telemetry *inside* the node.
- **Retrieval is deterministic** — it runs before the model on every turn, so grounding never
  depends on the model deciding to call a tool.
- **The model is injected** (``chat_model=``) or taken from the ``client.py`` seam; tests pass
  a fake. Same for the retriever.
- **Tools are optional**: pass ``tools=[...]`` to add a ``ToolNode`` loop
  (``answer → tools → answer`` until the model stops calling tools).

``ask()`` is the non-streaming entry point; ``streaming.py`` streams the same compiled graph.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.ai.config import get_ai_settings
from app.ai.prompts import render_prompt
from app.ai.telemetry import extract_usage, model_call_span, record_retrieval
from app.ai.tools.retrieve import DEFAULT_TOP_K, RetrievedChunk, Retriever, get_default_retriever


class GraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    context: list[RetrievedChunk]


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Numbered context block for the system prompt (the model cites ``[n]``)."""
    if not chunks:
        return "(no context available)"
    return "\n\n".join(
        f"[{i}] ({c.get('source') or 'unknown'})\n{c.get('content', '')}"
        for i, c in enumerate(chunks, start=1)
    )


def last_user_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    # Content blocks → join the text parts.
    parts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
    return "".join(parts)


def build_graph(
    *,
    chat_model: BaseChatModel | None = None,
    retriever: Retriever | None = None,
    tools: list[BaseTool] | None = None,
    top_k: int = DEFAULT_TOP_K,
    deployment_label: str | None = None,
) -> Any:
    """Compile the ``retrieve → answer`` graph. Nothing connects until the first run."""

    def _model() -> BaseChatModel:
        if chat_model is not None:
            return chat_model
        from app.ai.client import get_chat_model

        return get_chat_model()

    def _label() -> str:
        return deployment_label or get_ai_settings().chat_deployment or "unknown"

    bound_tools = list(tools or [])

    async def retrieve(state: GraphState) -> GraphState:
        question = last_user_text(state.get("messages", []))
        active = retriever if retriever is not None else get_default_retriever()
        started = time.perf_counter()
        try:
            chunks = await active.retrieve(question, top_k) if question else []
        except Exception:
            record_retrieval((time.perf_counter() - started) * 1000, "error")
            raise
        return {"context": chunks}

    async def answer(state: GraphState) -> GraphState:
        model = _model()
        if bound_tools:
            model = model.bind_tools(bound_tools)
        system = SystemMessage(
            content=render_prompt("system", context=format_context(state.get("context", [])))
        )
        with model_call_span(_label()) as call:
            response = await model.ainvoke([system, *state.get("messages", [])])
            call.set_usage(response)
        return {"messages": [response]}

    graph = StateGraph(GraphState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("answer", answer)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "answer")
    if bound_tools:
        graph.add_node("tools", ToolNode(bound_tools))
        graph.add_conditional_edges("answer", tools_condition, {"tools": "tools", END: END})
        graph.add_edge("tools", "answer")
    else:
        graph.add_edge("answer", END)
    return graph.compile()


@dataclass
class Answer:
    text: str
    sources: list[str] = field(default_factory=list)
    context: list[RetrievedChunk] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None


def unique_sources(chunks: list[RetrievedChunk]) -> list[str]:
    seen: list[str] = []
    for c in chunks:
        source = c.get("source") or ""
        if source and source not in seen:
            seen.append(source)
    return seen


async def ask(
    graph: Any,
    question: str,
    *,
    history: list[AnyMessage] | None = None,
    config: dict[str, Any] | None = None,
) -> Answer:
    """Run the graph once for ``question`` (with optional prior turns) and collect the answer."""
    inputs: GraphState = {
        "messages": [*(history or []), HumanMessage(content=question)],
        "context": [],
    }
    result = await graph.ainvoke(inputs, config)
    final = result["messages"][-1]
    text = _message_text(final) if isinstance(final, AIMessage) else str(final)
    input_tokens, output_tokens = extract_usage(final)
    context = result.get("context", []) or []
    return Answer(
        text=text,
        sources=unique_sources(context),
        context=context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
