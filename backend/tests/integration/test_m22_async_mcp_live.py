"""M22 integration: MCP demo via async graph ainvoke (skip if demo unavailable)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.agent.permissions import apply_permissions
from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools.mcp_loader import (
    load_mcp_tools_async,
    resolve_mcp_connections,
)

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def test_mcp_demo_ainvoke_without_nested_run() -> None:
    settings = _load_repo_settings()
    settings = settings.model_copy(update={"mcp_use_demo": True})
    conns = resolve_mcp_connections(settings)
    if not conns:
        pytest.skip("no MCP connections")

    async def _run() -> Any:
        tools = await load_mcp_tools_async(conns, sync_shim=True)
        tools = apply_permissions(tools, plan_mode=True)
        echo = next((t for t in tools if t.name == "echo"), None)
        if echo is None:
            pytest.skip("echo tool missing from MCP demo")

        class _LLM:
            def invoke(self, messages: list, config: Any = None) -> AIMessage:
                if any(isinstance(m, ToolMessage) for m in messages):
                    return AIMessage(content="echoed")
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "echo",
                            "args": {"text": "m22-async"},
                            "id": "c1",
                            "type": "tool_call",
                        }
                    ],
                )

        g = StateGraph(MessagesState)

        def call_model(state: MessagesState) -> dict:
            return {"messages": [_LLM().invoke(state["messages"])]}

        g.add_node("call_model", call_model)
        g.add_node("tools", ToolNode([echo]))
        g.add_edge(START, "call_model")

        def route(state: MessagesState) -> str:
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and last.tool_calls:
                return "tools"
            return END

        g.add_conditional_edges("call_model", route, {"tools": "tools", END: END})
        g.add_edge("tools", "call_model")
        app = g.compile()

        nested: list[int] = []
        real_run = asyncio.run

        def tracking_run(coro, *a, **k):
            try:
                asyncio.get_running_loop()
                nested.append(1)
            except RuntimeError:
                pass
            return real_run(coro, *a, **k)

        with patch(
            "mini_claude_code.tools.mcp_loader.asyncio.run",
            side_effect=tracking_run,
        ):
            result = await app.ainvoke(
                {"messages": [HumanMessage(content="echo")]},
                config={"recursion_limit": 8},
            )
        assert nested == [], "MCP sync shim asyncio.run must not run on ainvoke path"
        assert any(
            isinstance(m, ToolMessage) and "m22-async" in str(m.content)
            for m in result["messages"]
        )
        return result

    asyncio.run(_run())
