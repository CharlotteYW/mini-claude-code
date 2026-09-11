"""M32 unit tests: parallel vs serial fan-out, ask→serial, error isolation."""

from __future__ import annotations

import asyncio
import time

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from mini_claude_code.agent.permissions import apply_permissions
from mini_claude_code.agent.tool_fanout import (
    PolicyToolNode,
    batch_needs_serial,
    make_tools_node,
)

pytestmark = pytest.mark.unit

SLEEP_S = 0.2


def _compile(node: PolicyToolNode):
    g = StateGraph(MessagesState)
    g.add_node("tools", node)
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    return g.compile()


# Names must be READ_SAFE (add/echo) so parallel path is not forced serial by ask.
@tool("add")
def slow_a() -> str:
    """Slow auto tool A."""
    time.sleep(SLEEP_S)
    return "a"


@tool("echo")
def slow_b(text: str = "b") -> str:
    """Slow auto tool B."""
    time.sleep(SLEEP_S)
    return text or "b"


@tool("add")
def boom() -> str:
    """Always raises (name add → auto for fan-out mode)."""
    raise RuntimeError("boom")


@tool("echo")
def ok_tool(text: str = "ok") -> str:
    """Returns ok."""
    return text or "ok"


@tool
def write_file(path: str, content: str) -> str:
    """Mutating stub (ask by default policy name)."""
    return f"wrote {path}"


@tool
def read_file(path: str) -> str:
    """Read-safe stub."""
    return f"read {path}"


def _two_slow_calls() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "add", "args": {}, "id": "c-a", "type": "tool_call"},
            {"name": "echo", "args": {"text": "b"}, "id": "c-b", "type": "tool_call"},
        ],
    )


def test_batch_needs_serial_ask() -> None:
    assert batch_needs_serial(
        [{"name": "write_file"}], parallel=True, plan_mode=False
    )
    assert not batch_needs_serial(
        [{"name": "read_file"}], parallel=True, plan_mode=False
    )
    assert batch_needs_serial(
        [{"name": "read_file"}], parallel=False, plan_mode=False
    )


def test_parallel_faster_than_serial() -> None:
    parallel_node = make_tools_node([slow_a, slow_b], parallel=True)
    serial_node = make_tools_node([slow_a, slow_b], parallel=False)
    ai = _two_slow_calls()

    t0 = time.perf_counter()
    out_p = _compile(parallel_node).invoke({"messages": [ai]})
    wall_p = time.perf_counter() - t0
    assert parallel_node.last_mode == "parallel"

    t0 = time.perf_counter()
    out_s = _compile(serial_node).invoke({"messages": [ai]})
    wall_s = time.perf_counter() - t0
    assert serial_node.last_mode == "serial"

    contents_p = {
        m.content
        for m in out_p["messages"]
        if isinstance(m, ToolMessage)
    }
    contents_s = {
        m.content
        for m in out_s["messages"]
        if isinstance(m, ToolMessage)
    }
    assert contents_p == {"a", "b"}
    assert contents_s == {"a", "b"}
    assert wall_p < SLEEP_S * 1.6
    assert wall_s >= SLEEP_S * 1.6
    assert wall_p < wall_s * 0.85


def test_error_isolation_sibling_still_returns() -> None:
    node = make_tools_node([boom, ok_tool], parallel=True)
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "add", "args": {}, "id": "b", "type": "tool_call"},
            {"name": "echo", "args": {"text": "ok"}, "id": "o", "type": "tool_call"},
        ],
    )
    out = _compile(node).invoke({"messages": [ai]})
    by_id = {
        m.tool_call_id: m
        for m in out["messages"]
        if isinstance(m, ToolMessage)
    }
    assert "Error" in str(by_id["b"].content) or by_id["b"].status == "error"
    assert by_id["o"].content == "ok"
    assert node.last_mode == "parallel"


def test_ask_in_batch_forces_serial() -> None:
    tools = apply_permissions(
        [read_file, write_file],
        plan_mode=False,
        ask_callback=lambda _n, _a: True,
    )
    node = make_tools_node(tools, parallel=True, plan_mode=False)
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "read_file",
                "args": {"path": "a.txt"},
                "id": "r",
                "type": "tool_call",
            },
            {
                "name": "write_file",
                "args": {"path": "b.txt", "content": "x"},
                "id": "w",
                "type": "tool_call",
            },
        ],
    )
    out = _compile(node).invoke({"messages": [ai]})
    assert node.last_mode == "serial"
    tms = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert len(tms) == 2


def test_parallel_async_ainvoke() -> None:
    node = make_tools_node([slow_a, slow_b], parallel=True)
    ai = _two_slow_calls()

    async def _run() -> float:
        t0 = time.perf_counter()
        out = await _compile(node).ainvoke({"messages": [ai]})
        wall = time.perf_counter() - t0
        assert {
            m.content for m in out["messages"] if isinstance(m, ToolMessage)
        } == {"a", "b"}
        return wall

    wall = asyncio.run(_run())
    assert node.last_mode == "parallel"
    assert wall < SLEEP_S * 1.6
