"""M9 unit tests: permission resolve, Plan Mode, wrap deny/ask, fake-LLM graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.permissions import (
    apply_permissions,
    default_mode_for,
    make_cli_ask_callback,
    resolve_permission,
)
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.unit


def test_default_modes_read_vs_mutating() -> None:
    assert default_mode_for("read_file") == "auto"
    assert default_mode_for("glob_files") == "auto"
    assert default_mode_for("write_file") == "ask"
    assert default_mode_for("run_shell") == "ask"
    assert default_mode_for("remember_fact") == "ask"
    assert default_mode_for("mystery_tool") == "ask"


def test_plan_mode_forces_mutators_deny() -> None:
    assert resolve_permission("read_file", plan_mode=True) == "auto"
    assert resolve_permission("write_file", plan_mode=True) == "deny"
    assert resolve_permission("run_shell", plan_mode=True) == "deny"
    assert resolve_permission("git_commit", plan_mode=True) == "deny"
    # Unknown tools are not auto in Plan Mode.
    assert resolve_permission("mystery_tool", plan_mode=True) == "deny"


def test_denied_tool_does_not_call_body(tmp_path: Path) -> None:
    called: list[str] = []

    def write_file(path: str, content: str) -> str:
        called.append(path)
        (tmp_path / path).write_text(content)
        return "wrote"

    raw = StructuredTool.from_function(
        write_file,
        name="write_file",
        description="write",
    )
    wrapped = apply_permissions([raw], plan_mode=True, ask_callback=None)[0]
    out = wrapped.invoke({"path": "x.txt", "content": "nope"})
    assert "PERMISSION_DENIED" in str(out)
    assert "Plan Mode" in str(out)
    assert called == []
    assert not (tmp_path / "x.txt").exists()


def test_ask_approve_runs_tool(tmp_path: Path) -> None:
    def write_file(path: str, content: str) -> str:
        (tmp_path / path).write_text(content)
        return f"wrote {path}"

    raw = StructuredTool.from_function(
        write_file, name="write_file", description="write"
    )
    wrapped = apply_permissions(
        [raw],
        plan_mode=False,
        ask_callback=lambda _n, _a: True,
    )[0]
    out = wrapped.invoke({"path": "ok.txt", "content": "yes"})
    assert out == "wrote ok.txt"
    assert (tmp_path / "ok.txt").read_text() == "yes"


def test_ask_reject_and_none_callback_deny(tmp_path: Path) -> None:
    def write_file(path: str, content: str) -> str:
        (tmp_path / path).write_text(content)
        return "wrote"

    raw = StructuredTool.from_function(
        write_file, name="write_file", description="write"
    )
    rejected = apply_permissions(
        [raw], plan_mode=False, ask_callback=lambda _n, _a: False
    )[0]
    out = rejected.invoke({"path": "a.txt", "content": "x"})
    assert "PERMISSION_DENIED" in str(out)
    assert not (tmp_path / "a.txt").exists()

    no_cb = apply_permissions([raw], plan_mode=False, ask_callback=None)[0]
    out2 = no_cb.invoke({"path": "b.txt", "content": "x"})
    assert "PERMISSION_DENIED" in str(out2)
    assert "no interactive" in str(out2).lower() or "non-interactive" in str(out2).lower()


def test_cli_ask_callback_yes_no() -> None:
    answers = iter(["yes", "n"])
    cb = make_cli_ask_callback(
        input_fn=lambda _p: next(answers),
        output_fn=lambda _t: None,
    )
    assert cb("run_shell", {"command": "ls"}) is True
    assert cb("run_shell", {"command": "rm -rf /"}) is False


def test_toolnode_respects_plan_deny(tmp_path: Path) -> None:
    tools = apply_permissions(
        build_coding_tools(tmp_path),
        plan_mode=True,
        ask_callback=None,
    )
    g = StateGraph(MessagesState)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    compiled = g.compile()

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "blocked.txt", "content": "x"},
                "id": "c1",
                "type": "tool_call",
            }
        ],
    )
    out = compiled.invoke({"messages": [ai]})
    tm = out["messages"][-1]
    assert isinstance(tm, ToolMessage)
    assert "PERMISSION_DENIED" in str(tm.content)
    assert not (tmp_path / "blocked.txt").exists()


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
                        "args": {"path": "plan.txt", "content": "secret"},
                        "id": "w1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Could not write — permission denied.")


class _FakeLLMWrite:
    def __init__(self) -> None:
        self._bound = _FakeBoundWriteThenDone()

    def bind_tools(self, _tools: Any) -> _FakeBoundWriteThenDone:
        return self._bound


def test_graph_plan_mode_denies_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()

    graph = build_agent_graph(
        llm=_FakeLLMWrite(),
        tools=build_coding_tools(tmp_path),
        plan_mode=True,
        ask_callback=None,
    )
    names = set(graph.get_graph().nodes)
    assert "call_model" in names and "tools" in names

    result = graph.invoke(
        {"messages": [HumanMessage(content="write plan.txt")]},
        config={"recursion_limit": 10},
    )
    assert any(
        isinstance(m, ToolMessage) and "PERMISSION_DENIED" in str(m.content)
        for m in result["messages"]
    )
    assert not (tmp_path / "plan.txt").exists()
    get_settings.cache_clear()
