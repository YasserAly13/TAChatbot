# ADR-0009: LangChain + LangGraph on Azure AI Foundry as the AI runtime; Azure AI Search as the vector store

|        |            |
| ------ | ---------- |
| Status | Proposed   |
| Date   | 2026-09-28 |

## Context

The template exists to accelerate AI applications, yet until now it carried no AI code at all:
no model client, no orchestration, no retrieval, no telemetry for model calls. Every project
would have re-decided the runtime, re-wired authentication and re-invented the mock seam its
tests need. The team's decisions fix the surroundings: models are deployed on **Azure AI
Foundry** (an AI Services account with OpenAI model deployments, provisioned by Terraform —
ADR-0007), retrieval uses **Azure AI Search** (D7), the project database is Azure SQL and
external data is read through a read-only engine (ADR-0008), and the team named
**LangChain + LangGraph** as the orchestration layer. Constraints that shape the choice: the
api's OpenTelemetry stack is hard-pinned by the Azure distro (`0.61b0` / SDK `1.40`), the
Docker build is wheel-only on CPython 3.14, tests must stay offline, prompts and answers must
never reach the logs, and the deployed api authenticates with its managed identity.

## Decision

We ship an **`app/ai/` package** in `apps/api` as the AI runtime slot of the baseline:
**LangChain** (`langchain-core`, `langchain-openai`) for the model and embedding clients,
**LangGraph** for orchestration (a `StateGraph` skeleton with `retrieve → answer` nodes and a
tool registry), **Azure AI Search** (`azure-search-documents`) as the vector/hybrid store with
an ingestion job that owns the index definition, and a **read-only external-database tool**
that runs only allow-listed, parameterised queries through `app/db/external.py`. One factory
(`app/ai/client.py`) builds the chat and embedding clients — **managed identity** via
`DefaultAzureCredential` + `get_bearer_token_provider` when deployed, an API key only in dev —
and is the single **mock seam** for tests. Model calls are wrapped by `app/ai/telemetry.py`
(`gen_ai.*` span attributes, token/latency/failure metrics, a custom event) with **no prompt
or completion content** in logs or attributes. Streaming answers go through
`app/ai/streaming.py` as Server-Sent Events. All dependency pins ride beside — never
replace — the distro-pinned OTel line, and no LLM instrumentation package is added.

## Consequences

- Good: a project starts from a working, tested, telemetry-wired graph instead of a blank
  file; the `feature-scaffold` `ai`/`rag` targets copy this shape.
- Good: keyless in every deployed environment (identity roles are granted by the `ai-foundry`
  and `ai-search` Terraform modules); dev keys live in Key Vault and are optional.
- Good: tests run offline by swapping the client factory and retriever for fakes; an eval set
  gives prompt changes a regression check.
- Bad: LangChain/LangGraph move fast — versions are pinned exactly and bumped only via the
  `dependency-updater` agent with the Azure distro pins re-checked.
- Bad: the OTel GenAI instrumentation packages (`opentelemetry-instrumentation-openai-v2`,
  LangChain instrumentation) are **not** adopted: they would have to match the `0.61b0` line
  and would reintroduce prompt content capture we deliberately keep out. Telemetry is
  hand-rolled and therefore narrower.
- Bad: the ingestion job is synchronous (`SearchClient` in a thread); very large corpora need a
  proper batch pipeline the project writes.

## Alternatives considered

- **Azure AI Foundry Agent Service / `azure-ai-projects` only** — rejected as the baseline:
  it hides orchestration inside the platform and the team asked for LangGraph; it stays
  available to projects that want it.
- **Plain `openai` SDK without LangChain** — rejected: the team named LangChain/LangGraph, and
  the graph/tool abstractions are what the roadmap's skills scaffold against.
- **Semantic Kernel** — rejected for the same reason (team decision), not on merit.
- **pgvector / SQL-side vectors** — rejected: the database is Azure SQL (D6) and the team chose
  AI Search (D7); hybrid search and semantic ranking come for free.
- **OTel GenAI auto-instrumentation** — rejected for now (pin coupling and content capture);
  revisit when the distro's line includes it.

## References

- Related ADRs: ADR-0007 (Terraform modules `ai-foundry`, `ai-search`), ADR-0008 (external
  read-only engine the query tool uses)
- Docs: `docs/template-roadmap.md` (D7, Phase 4), `docs/architecture/ai.md`,
  `.claude/rules/70-ai.md`, `apps/api/app/ai/`
- External: LangChain OpenAI integration (`https://reference.langchain.com/python/integrations/langchain_openai/`),
  LangGraph (`https://langchain-ai.github.io/langgraph/`), Azure AI Search Python SDK
  (`https://learn.microsoft.com/python/api/overview/azure/search-documents-readme`), ODBC/SQL
  read-only tool → ADR-0008
