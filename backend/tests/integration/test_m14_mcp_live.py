"""M14 integration: real stdio in-repo MCP server via adapter (skip if deps fail)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.tools.mcp_loader import (
    default_demo_connections,
    load_mcp_tools_sync,
)
from mini_claude_code.agent.permissions import apply_permissions
from mini_claude_code.config import Settings

pytestmark = pytest.mark.integration


def _mcp_or_skip() -> list:
    try:
        tools = load_mcp_tools_sync(default_demo_connections())
    except Exception as exc:  # noqa: BLE001 — skip if adapter/server unavailable
        pytest.skip(f"MCP demo server unavailable: {exc}")
    if not tools:
        pytest.skip("MCP demo returned no tools")
    return tools


def test_stdio_echo_math_tools_load_and_invoke() -> None:
    tools = {t.name: t for t in _mcp_or_skip()}
    assert "echo" in tools
    assert "add" in tools
    assert tools["echo"].invoke({"text": "ping"}) == "ping"
    assert int(tools["add"].invoke({"a": 2, "b": 3})) == 5


class _FakeMcpCaller(BaseChatModel):
    """One tool call to MCP add, then a final answer."""

    def __init__(self) -> None:
        super().__init__()
        self._n = 0

    @property
    def _llm_type(self) -> str:
        return "fake-m14"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self._n += 1
        if self._n == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 10, "b": 7},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="sum is 17")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


def test_graph_can_call_mcp_add_tool(tmp_path) -> None:
    mcp_tools = _mcp_or_skip()
    # Narrow tool list: MCP only (still permission-wrapped).
    wrapped = apply_permissions(mcp_tools, plan_mode=False, ask_callback=lambda *_: True)
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        llm_model="x",
        workspace_root=str(tmp_path),
        context_compact_threshold=0,
        mcp_use_demo=False,
    )
    graph = build_agent_graph(
        settings=settings,
        llm=_FakeMcpCaller(),
        tools=wrapped,
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,  # already wrapped
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="add 10 and 7")]},
        config={"configurable": {"thread_id": "m14-int"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert "17" in str(tool_msgs[0].content) or tool_msgs[0].content == 17
    assert isinstance(result["messages"][-1], AIMessage)
    assert "17" in str(result["messages"][-1].content)
