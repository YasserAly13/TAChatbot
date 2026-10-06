"""Tool registry (ADR-0009).

A *tool* is a LangChain ``BaseTool`` the graph may let the model call. The registry is explicit
— a tool exists only if a module registers it — so a project sees exactly what the model can
reach. Built-ins:

- ``query_external_db`` — allow-listed, parameterised, read-only SQL (``query_external_db.py``).

Retrieval is NOT a model-callable tool by default: the graph runs it deterministically before
the model (``graph.py``) so every answer is grounded without depending on the model choosing
to call it. ``retrieve.py`` exposes the retriever used by that node.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

_REGISTRY: dict[str, BaseTool] = {}


def register_tool(tool: BaseTool) -> BaseTool:
    """Register (or replace) a tool by its name."""
    _REGISTRY[tool.name] = tool
    return tool


def get_tools() -> list[BaseTool]:
    """Tools currently registered, in registration order."""
    return list(_REGISTRY.values())


def _reset_for_tests() -> None:
    _REGISTRY.clear()
