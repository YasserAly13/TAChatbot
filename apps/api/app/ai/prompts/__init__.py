"""Versioned prompt files (ADR-0009).

Prompts are **files, not string literals**, so a change is a reviewable diff, the eval set
in ``tests/evals/`` can pin behaviour, and non-developers can read them. ``load_prompt("system")``
returns ``prompts/system.md``; ``{placeholders}`` are filled with ``str.format`` by the caller.
Never log a rendered prompt.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


class PromptNotFound(FileNotFoundError):
    """No ``<name>.md`` under ``app/ai/prompts/``."""


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """Return the text of ``prompts/<name>.md`` (cached; whitespace-stripped)."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptNotFound(f"prompt {name!r} not found at {path}")
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **values: str) -> str:
    """``load_prompt`` + ``str.format``; missing placeholders raise ``KeyError`` loudly."""
    return load_prompt(name).format(**values)
