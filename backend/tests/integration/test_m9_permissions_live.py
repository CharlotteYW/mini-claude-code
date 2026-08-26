"""M9 integration: Plan Mode denial path documented for live CLI (skip without LLM)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import get_settings
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.integration


def test_plan_mode_read_still_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake-LLM style contract test kept under integration marker as a live-ready sibling.

    Full Ollama demos stay manual (`./scripts/agent.sh --plan ...`); this pins the
    Plan Mode + read_file path without requiring a provider.
    """
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    (tmp_path / "note.txt").write_text("hello plan", encoding="utf-8")

    class _Bound:
        def __init__(self) -> None:
            self.n = 0

        def invoke(self, messages, config=None):
            self.n += 1
            if self.n == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"path": "note.txt"},
                            "id": "r1",
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content="note says hello plan")

    class _LLM:
        def bind_tools(self, _tools):
            return _Bound()

    graph = build_agent_graph(
        llm=_LLM(),
        tools=build_coding_tools(tmp_path),
        plan_mode=True,
        ask_callback=None,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="read note.txt")]},
        config={"recursion_limit": 10},
    )
    assert any(
        isinstance(m, ToolMessage) and "hello plan" in str(m.content)
        for m in result["messages"]
    )
    get_settings.cache_clear()


@pytest.mark.skipif(
    os.environ.get("MCC_LIVE_LLM", "").lower() not in {"1", "true", "yes"},
    reason="Set MCC_LIVE_LLM=1 with a working LLM_PROVIDER to run live Plan Mode demo.",
)
def test_live_plan_mode_write_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    graph = build_agent_graph(
        settings=settings,
        plan_mode=True,
        ask_callback=None,
    )
    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Call write_file exactly once to create secret.txt with "
                        "contents 'x'. Then stop."
                    )
                )
            ]
        },
        config={"recursion_limit": 8},
    )
    denied = any(
        isinstance(m, ToolMessage) and "PERMISSION_DENIED" in str(m.content)
        for m in result["messages"]
    )
    assert denied or not (tmp_path / "secret.txt").exists()
    get_settings.cache_clear()
