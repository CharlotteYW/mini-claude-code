"""M8 unit tests: AGENT.md inject + memory helpers (no Neo4j required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from mini_claude_code.agent.project_memory import (
    inject_project_memory,
    load_agent_md,
)
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.neo4j_facts import MemoryFact, format_facts_for_prompt

pytestmark = pytest.mark.unit


def test_inject_agent_md_prepends_system_message(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text(
        "Always use package manager PNPM_ONLY_XYZ.\n", encoding="utf-8"
    )
    messages = [HumanMessage(content="hi")]
    out = inject_project_memory(messages, tmp_path, ensure=False)
    assert isinstance(out[0], SystemMessage)
    assert "PNPM_ONLY_XYZ" in str(out[0].content)
    assert out[-1] == messages[0]


def test_inject_agent_md_idempotent(tmp_path: Path) -> None:
    (tmp_path / "AGENT.md").write_text("rule-one\n", encoding="utf-8")
    once = inject_project_memory([HumanMessage(content="a")], tmp_path)
    twice = inject_project_memory(once, tmp_path)
    assert sum(
        1
        for m in twice
        if isinstance(m, SystemMessage) and "AGENT.md" in str(m.content)
    ) == 1


def test_ensure_creates_template(tmp_path: Path) -> None:
    assert load_agent_md(tmp_path, ensure=True)
    assert (tmp_path / "AGENT.md").is_file()


def test_format_facts_for_prompt() -> None:
    block = format_facts_for_prompt(
        [MemoryFact(id="1", text="use pnpm", kind="pref")]
    )
    assert "use pnpm" in block
    assert "Neo4j" in block


def test_graph_prompt_includes_agent_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "AGENT.md").write_text(
        "MARKER_PROJECT_RULE_42\n", encoding="utf-8"
    )
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        WORKSPACE_ROOT=str(tmp_path),
        CONTEXT_COMPACT_THRESHOLD=0,
    )

    class _Bound:
        def __init__(self) -> None:
            self.last: list[Any] = []

        def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
            self.last = list(messages)
            return AIMessage(content="ok")

    bound = _Bound()

    class _LLM:
        def bind_tools(self, _tools: Any) -> _Bound:
            return bound

        def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
            return AIMessage(content="summary")

    graph = build_agent_graph(settings=settings, llm=_LLM(), tools=[])
    graph.invoke(
        {"messages": [HumanMessage(content="hello")]},
        config={"recursion_limit": 5},
    )
    assert any(
        isinstance(m, SystemMessage) and "MARKER_PROJECT_RULE_42" in str(m.content)
        for m in bound.last
    )
