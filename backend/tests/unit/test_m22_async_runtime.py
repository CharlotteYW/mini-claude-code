"""M22 unit tests: async permission/hook wraps + MCP without nested asyncio.run."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool, tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from mini_claude_code.agent.hooks import HookContext, HookRegistry, apply_hooks
from mini_claude_code.agent.permissions import apply_permissions
from mini_claude_code.agent.retry import ainvoke_with_retry, is_transient_llm_error
from mini_claude_code.tools.mcp_loader import (
    prepare_mcp_tool_async_only,
    wrap_mcp_tool_for_sync,
)

pytestmark = pytest.mark.unit


class _EchoArgs(BaseModel):
    x: str = Field(description="value")


class _AddArgs(BaseModel):
    x: int = Field(description="n")


def test_permission_wrap_exposes_coroutine() -> None:
    calls: list[str] = []

    async def _abody(x: str) -> str:
        calls.append(f"async:{x}")
        return f"ok:{x}"

    def _body(x: str) -> str:
        calls.append(f"sync:{x}")
        return f"ok:{x}"

    raw = StructuredTool(
        name="echo",
        description="echo",
        args_schema=_EchoArgs,
        func=_body,
        coroutine=_abody,
    )
    wrapped = apply_permissions([raw], plan_mode=False)[0]
    assert wrapped.coroutine is not None
    assert asyncio.run(wrapped.ainvoke({"x": "a"})) == "ok:a"
    assert calls == ["async:a"]


def test_permission_ainvoke_does_not_call_asyncio_run() -> None:
    async def _abody(x: str) -> str:
        return f"ok:{x}"

    raw = StructuredTool(
        name="echo",
        description="echo",
        args_schema=_EchoArgs,
        coroutine=_abody,
    )
    wrapped = apply_permissions([raw], plan_mode=False)[0]

    real_run = asyncio.run
    with patch("asyncio.run", side_effect=AssertionError("asyncio.run should not run")):
        out = real_run(wrapped.ainvoke({"x": "z"}))
    assert out == "ok:z"


def test_hooks_wrap_preserves_ainvoke() -> None:
    async def _abody(x: str) -> str:
        return f"ok:{x}"

    raw = StructuredTool(
        name="echo",
        description="echo",
        args_schema=_EchoArgs,
        coroutine=_abody,
    )

    def allow(ctx: HookContext) -> bool:
        return True

    registry = HookRegistry(pre=[allow], post=[], stop=[])
    wrapped = apply_hooks([raw], registry)[0]
    assert wrapped.coroutine is not None
    assert asyncio.run(wrapped.ainvoke({"x": "h"})) == "ok:h"


def test_wrap_mcp_sync_shim_flag() -> None:
    class _Fake:
        name = "echo"
        description = "echo"
        args_schema = None

        async def ainvoke(self, payload: Any, config: Any = None) -> str:
            return "mcp-ok"

    prepared = wrap_mcp_tool_for_sync(_Fake())  # type: ignore[arg-type]
    assert getattr(prepared, "_mcc_mcp_sync_shim") is True
    assert prepared.coroutine is not None
    assert prepared.func is not None

    async_only = prepare_mcp_tool_async_only(_Fake())  # type: ignore[arg-type]
    assert getattr(async_only, "_mcc_mcp_sync_shim") is False
    assert async_only.coroutine is not None


def test_ainvoke_graph_with_async_only_tool() -> None:
    """Async graph path runs coroutine-only tools without sync shim."""

    async def _abody(x: int) -> str:
        return str(x + 1)

    tool_obj = StructuredTool(
        name="add",
        description="add",
        args_schema=_AddArgs,
        coroutine=_abody,
    )
    tool_obj = apply_permissions([tool_obj], plan_mode=False)[0]

    class _LLM:
        def bind_tools(self, _tools: Any) -> "_LLM":
            return self

        async def ainvoke(self, messages: list, config: Any = None) -> AIMessage:
            if any(isinstance(m, ToolMessage) for m in messages):
                return AIMessage(content="done")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"x": 41},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )

        def invoke(self, messages: list, config: Any = None) -> AIMessage:
            return asyncio.run(self.ainvoke(messages, config))

    g = StateGraph(MessagesState)

    def call_model(state: MessagesState) -> dict:
        llm = _LLM()
        return {"messages": [llm.invoke(state["messages"])]}

    g.add_node("call_model", call_model)
    g.add_node("tools", ToolNode([tool_obj]))
    g.add_edge(START, "call_model")

    def route(state: MessagesState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    g.add_conditional_edges("call_model", route, {"tools": "tools", END: END})
    g.add_edge("tools", "call_model")
    app = g.compile()

    nested_runs: list[int] = []
    real_run = asyncio.run

    def tracking_run(coro, *args, **kwargs):
        try:
            asyncio.get_running_loop()
            nested_runs.append(1)
        except RuntimeError:
            pass
        return real_run(coro, *args, **kwargs)

    with patch("asyncio.run", side_effect=tracking_run):
        result = real_run(
            app.ainvoke(
                {"messages": [HumanMessage(content="add")]},
                config={"recursion_limit": 8},
            )
        )
    assert nested_runs == []
    assert any(
        isinstance(m, ToolMessage) and m.content == "42" for m in result["messages"]
    )


def test_ainvoke_with_retry_transient() -> None:
    n = {"i": 0}

    async def flaky() -> str:
        n["i"] += 1
        if n["i"] < 2:
            raise ConnectionError("blip")
        return "ok"

    out = asyncio.run(
        ainvoke_with_retry(flaky, max_attempts=3, backoff_sec=0.0)
    )
    assert out == "ok"
    assert n["i"] == 2


def test_is_transient_still_works() -> None:
    assert is_transient_llm_error(ConnectionError("x"))


def test_sync_graph_invoke_still_works_with_permission_wrap() -> None:
    @tool
    def echo(text: str) -> str:
        """Echo text."""
        return text

    wrapped = apply_permissions([echo], plan_mode=False)[0]
    assert wrapped.invoke({"text": "hi"}) == "hi"
