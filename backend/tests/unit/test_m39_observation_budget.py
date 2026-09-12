"""M39 unit tests: observation budget truncate / summarize / PolicyToolNode."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from mini_claude_code.agent.observation_budget import (
    apply_budget_to_tool_message,
    apply_budget_to_tool_outputs,
    apply_observation_budget,
    truncate_head_tail,
)
from mini_claude_code.agent.tool_fanout import PolicyToolNode
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.unit


def test_under_budget_unchanged() -> None:
    text = "hello world"
    result = apply_observation_budget(text, max_chars=100)
    assert result.truncated is False
    assert result.summarized is False
    assert result.content == text


def test_over_budget_head_tail_marker() -> None:
    text = "HEAD" + ("m" * 200) + "TAIL"
    result = apply_observation_budget(text, max_chars=80, head_ratio=0.5)
    assert result.truncated is True
    assert "obs-budget truncated" in str(result.content)
    assert str(result.content).startswith("HEAD")
    assert str(result.content).endswith("TAIL")
    assert len(str(result.content)) <= 80 + 40  # marker overhead bound


def test_truncate_head_tail_helper() -> None:
    out = truncate_head_tail("A" * 100, 40, head_ratio=0.5)
    assert "obs-budget truncated" in out
    assert out.startswith("A")
    assert out.endswith("A")


def test_summarize_when_huge() -> None:
    calls: list[str] = []

    def summarizer(name: str, content: str) -> str:
        calls.append(name)
        return "SHORT_SUMMARY"

    huge = "X" * 500
    result = apply_observation_budget(
        huge,
        max_chars=100,
        tool_name="run_shell",
        summarize=True,
        summarizer=summarizer,
    )
    assert calls == ["run_shell"]
    assert result.summarized is True
    assert "SHORT_SUMMARY" in str(result.content)
    assert len(str(result.content)) < 200


def test_summarize_not_called_below_2x() -> None:
    calls: list[int] = []

    def summarizer(name: str, content: str) -> str:
        calls.append(1)
        return "nope"

    # 150 chars, budget 100 → over budget but < 2× → truncate only
    result = apply_observation_budget(
        "y" * 150,
        max_chars=100,
        summarize=True,
        summarizer=summarizer,
    )
    assert calls == []
    assert result.truncated is True
    assert result.summarized is False


def test_disabled_max_chars() -> None:
    huge = "z" * 10_000
    result = apply_observation_budget(huge, max_chars=0)
    assert result.truncated is False
    assert result.content == huge


def test_apply_to_tool_message_and_outputs() -> None:
    msg = ToolMessage(content="q" * 500, tool_call_id="1", name="run_shell")
    out = apply_budget_to_tool_message(msg, max_chars=120)
    assert isinstance(out, ToolMessage)
    assert "obs-budget" in str(out.content)

    bundled = apply_budget_to_tool_outputs(
        {"messages": [msg]},
        max_chars=120,
    )
    assert "obs-budget" in str(bundled["messages"][0].content)


def test_policy_tool_node_applies_budget() -> None:
    @tool("echo")
    def dump_noise() -> str:
        """Return a long string (named echo → auto permission)."""
        return "START" + ("n" * 400) + "END"

    node = PolicyToolNode(
        [dump_noise],
        parallel=False,
        observation_max_chars=100,
        observation_summarize=False,
    )
    g = StateGraph(MessagesState)
    g.add_node("tools", node)
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    graph = g.compile()
    result = graph.invoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "echo",
                            "args": {},
                            "id": "c1",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        }
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    body = str(tool_msgs[0].content)
    assert "obs-budget" in body
    assert "START" in body[:30]
    assert "END" in body


def test_settings_defaults() -> None:
    get_settings.cache_clear()
    s = Settings(_env_file=None)
    assert s.tool_observation_max_chars == 32_000
    assert s.tool_observation_summarize is False
