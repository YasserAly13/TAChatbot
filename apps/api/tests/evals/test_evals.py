"""Prompt regression harness (rule 70 → Testing).

Offline by default: each case scripts the model's answer, so what is actually checked is the
**pipeline around the prompt** — retrieval reaches the prompt, sources are surfaced, the system
prompt still carries its placeholders and rules. Extend ``cases.json`` whenever a prompt file
changes. A live-model tier is opt-in: set ``AI_EVAL_LIVE=true`` with real ``AZURE_AI_*``
settings and the scripted answer is replaced by the deployment's own.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from app.ai.graph import ask, build_graph
from app.ai.prompts import load_prompt
from tests.ai.fakes import FakeRetriever, fake_chat_model

CASES = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
LIVE = os.getenv("AI_EVAL_LIVE", "").lower() == "true"


def _model_for(case: dict):
    if LIVE:
        from app.ai.client import get_chat_model

        return get_chat_model()
    return fake_chat_model(case["scripted_answer"])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_case(case: dict) -> None:
    retriever = FakeRetriever(case["context"])
    graph = build_graph(chat_model=_model_for(case), retriever=retriever, deployment_label="eval")
    answer = asyncio.run(ask(graph, case["question"]))
    assert retriever.calls and retriever.calls[0][0] == case["question"]
    for needle in case["expect_contains"]:
        assert needle.lower() in answer.text.lower(), (case["id"], answer.text)
    assert answer.sources == case["expect_sources"]


def test_system_prompt_keeps_its_guardrails() -> None:
    prompt = " ".join(load_prompt("system").lower().split())  # collapse line wraps
    assert "{context}" in prompt
    assert "do not know" in prompt  # refuses to invent
    assert "cite" in prompt  # citations
    assert "context is data" in prompt  # injection guard
