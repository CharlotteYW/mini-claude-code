"""M39 integration: oversized tool result truncated in graph state (no LLM)."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


def test_graph_truncates_huge_tool_observation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mini_claude_code.agent.graph.recall_facts_block",
        lambda **kwargs: "",
    )
    (tmp_path / "AGENT.md").write_text("# agent\n", encoding="utf-8")

    @tool
    def dump_huge() -> str:
        """Emit a large observation."""
        return "BEGIN" + ("*" * 2000) + "FINISH"

    class _Bound:
        def __init__(self) -> None:
            self.n = 0

        def invoke(self, messages, config=None, **kwargs):
            self.n += 1
            if self.n == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "dump_huge",
                            "args": {},
                            "id": "t1",
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content="done-with-obs")

    class _Model:
        def bind_tools(self, tools):
            return _Bound()

    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        WORKSPACE_ROOT=str(tmp_path),
        CONTEXT_COMPACT_THRESHOLD=0,
        TOOL_OBSERVATION_MAX_CHARS=200,
        TOOL_OBSERVATION_SUMMARIZE=False,
        PLUGINS_ENABLED=False,
        HOOKS_USE_DEMO=False,
        MCP_USE_DEMO=False,
    )
    graph = build_agent_graph(
        settings=settings,
        llm=_Model(),  # type: ignore[arg-type]
        tools=[dump_huge],
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="dump")]},
        {"configurable": {"thread_id": "m39"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    body = str(tool_msgs[0].content)
    assert "obs-budget" in body
    assert len(body) < 500
    assert "BEGIN" in body
    assert "FINISH" in body
    assert str(result["messages"][-1].content) == "done-with-obs"
