# AI runtime

`apps/api/app/ai/` is the **AI runtime slot** of the baseline
([ADR-0009](../adr/0009-ai-runtime-langchain-langgraph-foundry.md)): LangChain + LangGraph on
Azure AI Foundry model deployments, Azure AI Search for retrieval, and a read-only tool over an
external database. It ships **no use case** — a compiled `retrieve → answer` graph a project
copies, a tool registry, prompt files, telemetry, streaming and an ingestion job — so the first
AI feature starts from something tested instead of a blank file. The enforced conventions are
[`.claude/rules/70-ai.md`](../../.claude/rules/70-ai.md).

---

## Shape

```mermaid
flowchart LR
    route["/v1 route (project)<br/>build_graph() · ask() / stream_answer()"]
    graph["app/ai/graph.py<br/>StateGraph: retrieve → answer (→ tools loop)"]
    ret["app/ai/tools/retrieve.py<br/>AzureSearchRetriever | NullRetriever"]
    client["app/ai/client.py<br/>get_chat_model() · get_embeddings()  ← mock seam"]
    tel["app/ai/telemetry.py<br/>model_call_span · record_retrieval"]
    tools["app/ai/tools/query_external_db.py<br/>allow-listed, parameterised, read-only"]
    prompts["app/ai/prompts/*.md<br/>load_prompt()"]
    ingest["app/ai/ingest.py<br/>chunk → embed → upload · owns the index"]

    foundry["Azure AI Foundry<br/>chat + embedding deployments"]
    search[("Azure AI Search<br/>hybrid index")]
    ext[("External Azure SQL<br/>read-only engine")]
    azm["Azure Monitor"]

    route --> graph
    graph --> ret --> search
    ret --> client
    graph --> client --> foundry
    graph --> prompts
    graph -.-> tools --> ext
    graph --> tel -.-> azm
    ingest --> client
    ingest --> search
```

---

## The pieces

**`config.py`.** `get_ai_settings()` snapshots the `AZURE_AI_*` / `AZURE_SEARCH_*` / `AI_*`
variables (full list in the [environment reference](../reference/environment-variables.md)).
Everything is optional: with nothing set the service boots and only a feature that actually
calls the AI layer raises `AINotConfigured`. A mistyped `AZURE_AI_AUTH_MODE` raises — there is
no silent fallback to a key.

**`client.py` — the mock seam.** The only place a model or embedding client is built.
`build_chat_model()` / `build_embeddings()` construct `AzureChatOpenAI` /
`AzureOpenAIEmbeddings` with the deployment, API version, timeout, retries and — deployed —
a bearer-token provider from `DefaultAzureCredential` for the Cognitive Services scope (the
user-assigned identity is selected through `AZURE_CLIENT_ID`, which the use-case Bicep sets; the
cloud team grants it _Cognitive Services OpenAI User_ on the shared Foundry via `infra/grant-request.md`). `api_key` mode exists for local
development only. Nothing connects at construction; `stream_usage=True` makes Azure OpenAI
report token usage on streamed answers too.

**`graph.py`.** `build_graph(chat_model=None, retriever=None, tools=None, top_k=5)` compiles a
`StateGraph` over a typed state (`messages` with the `add_messages` reducer, `context`):

1. `retrieve` — embeds the latest user turn and queries the retriever (deterministically, every
   turn — grounding never depends on the model choosing a tool); records retrieval telemetry.
2. `answer` — renders `prompts/system.md` with the numbered context, calls the model inside
   `model_call_span()`, appends the `AIMessage`.
3. optional `tools` — when tools are passed, the model is bound to them and a `ToolNode` loop
   (`answer → tools → answer`) runs until it stops calling tools.

`ask(graph, question, history=…)` is the non-streaming entry point and returns the answer text,
the unique sources, the context and the token usage.

**`streaming.py`.** `stream_answer()` drives the same graph with LangGraph's `updates` +
`messages` stream modes and yields Server-Sent Events: `sources` (after retrieval), `token`
(per model chunk), `done` (sources + usage) or `error` (a bounded `error_kind`, never the
exception message). `sse_response()` wraps it in a `StreamingResponse` with proxy buffering
disabled. The BFF forwards it with the streaming pass-through helper, not `fetchUpstream`.

**`tools/`.** An explicit registry (`register_tool` / `get_tools`). The built-in
`query_external_db` tool runs **allow-listed** queries from `tools/queries.py` — fixed
parameterised `SELECT`s with typed parameters the model fills in — through the read-only
external engine ([data.md](data.md)). Three layers keep it read-only: the allow-list (the model
never writes SQL), the engine's non-`SELECT` guard, and the SELECT-only login the data owner
provides. `AI_ALLOW_TEXT_TO_SQL=true` unlocks model-written `SELECT`s and is a project decision
that needs a threat model first. The template ships an **empty** allow-list.

**`tools/retrieve.py`.** `AzureSearchRetriever` embeds the query and runs a **hybrid** search
(keyword + `VectorizedQuery`) against the index, in a worker thread (the sync SDK client; the
async client would add `aiohttp` for no gain). `get_default_retriever()` picks it when both
the search index and an embedding deployment are configured, otherwise `NullRetriever` — the
graph still answers, with an empty context.

**`ingest.py`.** The RAG ingestion job owns the index definition (`build_index`: `id`,
`content`, `source`, `chunk_index`, `content_vector` with an HNSW profile sized by
`AZURE_AI_EMBEDDING_DIMENSIONS`) so the retriever and the index cannot drift. `ensure_index` is
idempotent; `ingest_documents` chunks (fixed windows with overlap), embeds in batches and
uploads with stable ids (re-ingesting a source overwrites its chunks). Run it from `apps/api`:
`uv run python -m app.ai.ingest ./docs`. The identity needs _Search Index Data Contributor_ +
_Search Service Contributor_ (granted to the api identity by the `ai-search` module; a dev key
works locally).

**`prompts/`.** Prompts are files. `load_prompt("system")` reads `prompts/system.md`;
`render_prompt` fills `{placeholders}` and fails loudly on a missing one. The shipped system
prompt grounds the answer in the numbered context, requires `[n]` citations, refuses to invent,
and states that context is data, not instructions.

**`telemetry.py`.** `model_call_span(deployment)` wraps every model call: a span named
`gen_ai.chat` with `gen_ai.system`, `gen_ai.operation.name`, `gen_ai.request.model`, the
`trace_id`, and — after the call — `gen_ai.usage.input_tokens` / `output_tokens`; metrics
`ai-accelerator.ai.model.duration`, `.model.tokens`, `.model.failures`, `.retrieval.duration`
(bounded attributes: deployment, outcome, token type, error kind); one `ai.model_call` custom
event; one structured log line. **No prompt, completion, retrieved text or user identifier
anywhere.** The OTel GenAI auto-instrumentation packages are deliberately not used (pin coupling
with the distro's `0.61b0` line and content capture).

---

## Using it from a route

```python
# apps/api/app/routers/assistant.py  (a project's feature — the template ships no route)
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai.graph import ask, build_graph
from app.ai.streaming import sse_response, stream_answer

router = APIRouter(prefix="/assistant", tags=["assistant"])
_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = build_graph()  # client + retriever from settings, lazily
    return _graph


class AskIn(BaseModel):
    question: str


@router.post("/ask")
async def ask_route(body: AskIn) -> dict:
    answer = await ask(graph(), body.question)
    return {"answer": answer.text, "sources": answer.sources}


@router.post("/ask/stream")
async def ask_stream(body: AskIn):
    return sse_response(stream_answer(graph(), body.question))
```

Attach it to `v1_router` (rule 05). The BFF calls `/v1/assistant/ask` with `fetchUpstream`
(raising the hop timeout via `signal` — a model call routinely exceeds 10 s) and
`/v1/assistant/ask/stream` with the streaming pass-through helper.

---

## Testing

Everything runs offline by swapping the seam ([`tests/ai/fakes.py`](../../apps/api/tests/ai/fakes.py)):
`GenericFakeChatModel` for the model, `FakeRetriever`, `FakeEmbeddings`, `FakeSearchClient`,
and a fake external `session_factory`. `tests/ai/` covers configuration, the client factory's
auth selection, the graph, streaming, tools, retrieval, ingestion and telemetry;
`tests/evals/` is the **prompt regression harness** — `cases.json` scripts the model's answer so
the pipeline around the prompt (retrieval → prompt → sources → citations) is pinned; extend it
whenever a prompt changes. A live-model tier is opt-in (`AI_EVAL_LIVE=true`).

---

## What a project adds

- Its **routes** under `/v1` (above) and the BFF routes/UI that call them.
- Its **prompt files** and eval cases.
- Its **allow-listed queries** in `tools/queries.py` (or registered at startup) and any new
  tools — each with a fake-backed test and a threat-model note.
- Its **ingestion sources** (what `python -m app.ai.ingest` reads) and, when the corpus outgrows
  the job, an indexer pipeline.
- Threat modelling for prompt injection, data exfiltration through tools, and PII in chat
  history — the baseline gives the controls; the project decides the data classification.

## Related

- [ADR-0009](../adr/0009-ai-runtime-langchain-langgraph-foundry.md) — the decision and the
  alternatives rejected.
- [data.md](data.md) — the read-only external engine the query tool uses.
- [observability.md](observability.md) — where the `gen_ai` spans and `ai-accelerator.ai.*`
  metrics land.
- The shared Foundry and AI Search service (platform tier) and the project's index — [`infra/README.md`](../../infra/README.md), [`infra/platform/README.md`](../../infra/platform/README.md).
