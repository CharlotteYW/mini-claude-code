"""M10 unit tests: interrupt on ask, Command resume, HITL helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.hitl import (
    format_approval_prompt,
    invoke_with_hitl,
    pending_interrupt_values,
    result_interrupt_values,
)
from mini_claude_code.agent.permissions import apply_permissions
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.unit


def test_format_approval_prompt() -> None:
    text = format_approval_prompt(
        {"type": "tool_approval", "tool": "write_file", "args": {"path": "a.txt"}}
    )
    assert "write_file" in text
    assert "a.txt" in text


def test_ask_interrupt_then_resume_approve(tmp_path: Path) -> None:
    tools = apply_permissions(
        build_coding_tools(tmp_path),
        plan_mode=False,
        ask_callback=None,
    )
    g = StateGraph(MessagesState)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    graph = g.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "m10-approve"}}

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "ok.txt", "content": "hi"},
                "id": "c1",
                "type": "tool_call",
            }
        ],
    )
    result = graph.invoke({"messages": [ai]}, config=config)
    pending = result_interrupt_values(result)
    assert pending
    assert pending[0]["tool"] == "write_file"
    assert not (tmp_path / "ok.txt").exists()

    result2 = graph.invoke(Command(resume=True), config=config)
    tm = result2["messages"][-1]
    assert isinstance(tm, ToolMessage)
    assert "PERMISSION_DENIED" not in str(tm.content)
    assert (tmp_path / "ok.txt").read_text() == "hi"


def test_ask_interrupt_then_resume_reject(tmp_path: Path) -> None:
    tools = apply_permissions(
        build_coding_tools(tmp_path),
        plan_mode=False,
        ask_callback=None,
    )
    g = StateGraph(MessagesState)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    graph = g.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "m10-reject"}}

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "no.txt", "content": "x"},
                "id": "c1",
                "type": "tool_call",
            }
        ],
    )
    graph.invoke({"messages": [ai]}, config=config)
    assert pending_interrupt_values(graph, config)
    result2 = graph.invoke(Command(resume=False), config=config)
    tm = result2["messages"][-1]
    assert isinstance(tm, ToolMessage)
    assert "PERMISSION_DENIED" in str(tm.content)
    assert not (tmp_path / "no.txt").exists()


def test_auto_and_plan_never_interrupt(tmp_path: Path) -> None:
    (tmp_path / "r.txt").write_text("hello", encoding="utf-8")
    tools = apply_permissions(
        build_coding_tools(tmp_path),
        plan_mode=True,
        ask_callback=None,
    )
    g = StateGraph(MessagesState)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    graph = g.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "m10-plan"}}

    # write denied without interrupt
    ai_w = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "x.txt", "content": "no"},
                "id": "w1",
                "type": "tool_call",
            }
        ],
    )
    out_w = graph.invoke({"messages": [ai_w]}, config=config)
    assert not result_interrupt_values(out_w)
    assert "PERMISSION_DENIED" in str(out_w["messages"][-1].content)

    # read auto without interrupt
    config2 = {"configurable": {"thread_id": "m10-plan-read"}}
    ai_r = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "read_file",
                "args": {"path": "r.txt"},
                "id": "r1",
                "type": "tool_call",
            }
        ],
    )
    out_r = graph.invoke({"messages": [ai_r]}, config=config2)
    assert not result_interrupt_values(out_r)
    assert "hello" in str(out_r["messages"][-1].content)


class _FakeBoundWriteThenDone:
    def __init__(self) -> None:
        self.n = 0

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        self.n += 1
        if self.n == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"path": "hitl.txt", "content": "secret"},
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="done after hitl")


class _FakeLLMWrite:
    def __init__(self) -> None:
        self._bound = _FakeBoundWriteThenDone()

    def bind_tools(self, _tools: Any) -> _FakeBoundWriteThenDone:
        return self._bound


def test_graph_hitl_approve_via_invoke_with_hitl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()

    graph = build_agent_graph(
        llm=_FakeLLMWrite(),
        tools=build_coding_tools(tmp_path),
        checkpointer=MemorySaver(),
        plan_mode=False,
        ask_callback=None,
    )
    config = {
        "recursion_limit": 10,
        "configurable": {"thread_id": "m10-graph"},
    }
    answers = iter([True])
    result, code = invoke_with_hitl(
        graph,
        "write hitl.txt",
        config,
        approve_fn=lambda _p: next(answers),
    )
    assert code == 0
    assert result is not None
    assert (tmp_path / "hitl.txt").read_text() == "secret"
    assert any(isinstance(m, HumanMessage) for m in result["messages"])
    get_settings.cache_clear()


def test_topology_unchanged(tmp_path: Path) -> None:
    graph = build_agent_graph(
        llm=_FakeLLMWrite(),
        tools=build_coding_tools(tmp_path),
        checkpointer=MemorySaver(),
        plan_mode=False,
    )
    names = set(graph.get_graph().nodes)
    assert "call_model" in names and "tools" in names
