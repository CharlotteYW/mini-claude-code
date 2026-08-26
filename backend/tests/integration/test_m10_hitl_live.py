"""M10 integration: HITL interrupt + resume (MemorySaver; optional live)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.hitl import invoke_with_hitl
from mini_claude_code.config import get_settings
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.integration


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
                        "name": "write_file",
                        "args": {"path": "live.txt", "content": "ok"},
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="wrote after approval")


class _LLM:
    def bind_tools(self, _tools):
        return _Bound()


def test_hitl_approve_and_reject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    graph = build_agent_graph(
        llm=_LLM(),
        tools=build_coding_tools(tmp_path),
        checkpointer=MemorySaver(),
        plan_mode=False,
        ask_callback=None,
    )
    cfg_ok = {
        "recursion_limit": 10,
        "configurable": {"thread_id": "int-approve"},
    }
    result, code = invoke_with_hitl(
        graph, "write", cfg_ok, approve_fn=lambda _p: True
    )
    assert code == 0
    assert (tmp_path / "live.txt").read_text() == "ok"
    assert result is not None

    # Fresh fake LLM instance for reject path
    graph2 = build_agent_graph(
        llm=_LLM(),
        tools=build_coding_tools(tmp_path),
        checkpointer=MemorySaver(),
        plan_mode=False,
        ask_callback=None,
    )
    cfg_no = {
        "recursion_limit": 10,
        "configurable": {"thread_id": "int-reject"},
    }
    result2, code2 = invoke_with_hitl(
        graph2, "write", cfg_no, approve_fn=lambda _p: False
    )
    assert code2 == 0
    assert result2 is not None
    assert any(
        isinstance(m, ToolMessage) and "PERMISSION_DENIED" in str(m.content)
        for m in result2["messages"]
    )
    get_settings.cache_clear()


@pytest.mark.skipif(
    os.environ.get("MCC_LIVE_LLM", "").lower() not in {"1", "true", "yes"},
    reason="Set MCC_LIVE_LLM=1 for live HITL demo.",
)
def test_live_hitl_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    graph = build_agent_graph(
        settings=settings,
        checkpointer=MemorySaver(),
        plan_mode=False,
        ask_callback=None,
    )
    config = {
        "recursion_limit": 8,
        "configurable": {"thread_id": "live-hitl"},
    }
    result, code = invoke_with_hitl(
        graph,
        "Call write_file once to create secret.txt with contents x, then stop.",
        config,
        approve_fn=lambda _p: True,
    )
    assert code == 0
    assert result is not None
    get_settings.cache_clear()
