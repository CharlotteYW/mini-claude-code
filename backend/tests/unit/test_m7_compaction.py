"""M7 unit tests: compaction helpers and safe tool-message cuts."""

from __future__ import annotations

from typing import Any, Sequence

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from mini_claude_code.agent.compact import (
    estimate_tokens,
    maybe_compact_messages,
    safe_prefix_end,
)
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.unit


def _long_human(n: int = 400) -> HumanMessage:
    return HumanMessage(content=("goal-alpha " * n).strip())


def test_below_threshold_unchanged_summarizer_not_called() -> None:
    calls: list[int] = []

    def summarizer(prefix: Sequence[BaseMessage]) -> BaseMessage:
        calls.append(len(prefix))
        return SystemMessage(content="should-not-run")

    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    out, did = maybe_compact_messages(
        messages,
        threshold_tokens=10_000,
        keep_recent=4,
        summarizer=summarizer,
    )
    assert did is False
    assert out == messages
    assert calls == []


def test_above_threshold_replaces_prefix_with_summary() -> None:
    seen: list[str] = []

    def summarizer(prefix: Sequence[BaseMessage]) -> BaseMessage:
        blob = " ".join(str(getattr(m, "content", "")) for m in prefix)
        seen.append(blob)
        return SystemMessage(content="[conversation summary]\nkept goal-alpha")

    messages = [
        _long_human(200),
        AIMessage(content="ack1 " + ("x" * 200)),
        _long_human(200),
        AIMessage(content="ack2 " + ("y" * 200)),
        HumanMessage(content="recent-question"),
        AIMessage(content="recent-answer"),
    ]
    assert estimate_tokens(messages) > 100

    out, did = maybe_compact_messages(
        messages,
        threshold_tokens=100,
        keep_recent=2,
        summarizer=summarizer,
    )
    assert did is True
    assert isinstance(out[0], SystemMessage)
    assert "goal-alpha" in seen[0]
    assert out[-2:] == messages[-2:]
    assert estimate_tokens(out) < estimate_tokens(messages)


def test_safe_prefix_end_does_not_orphan_tool_messages() -> None:
    messages = [
        HumanMessage(content="do add"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "add",
                    "args": {"a": 1, "b": 2},
                    "id": "c1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="3", tool_call_id="c1", name="add"),
        AIMessage(content="sum is 3"),
    ]
    cut = safe_prefix_end(messages, keep_recent=1)
    recent = messages[cut:]
    assert not isinstance(recent[0], ToolMessage)
    for i, m in enumerate(recent):
        if isinstance(m, AIMessage) and m.tool_calls:
            ids = {tc["id"] for tc in m.tool_calls}
            later = recent[i + 1 :]
            assert any(
                isinstance(t, ToolMessage) and t.tool_call_id in ids for t in later
            )


def test_graph_compacts_then_invokes_with_rewritten_state() -> None:
    settings = Settings(
        _env_file=None,
        CONTEXT_COMPACT_THRESHOLD=80,
        CONTEXT_KEEP_RECENT=2,
    )
    get_settings.cache_clear()

    class _Bound:
        def __init__(self) -> None:
            self.last_messages: list[Any] = []

        def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
            self.last_messages = list(messages)
            return AIMessage(content="final")

    bound = _Bound()

    class _LLM:
        def bind_tools(self, _tools: Any) -> _Bound:
            return bound

        def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
            return AIMessage(content="summary-body")

    graph = build_agent_graph(settings=settings, llm=_LLM(), tools=[])
    history = [
        _long_human(80),
        AIMessage(content="old-a " + ("a" * 80)),
        _long_human(80),
        AIMessage(content="old-b " + ("b" * 80)),
        HumanMessage(content="newest"),
    ]
    result = graph.invoke(
        {"messages": history},
        config={"recursion_limit": 10},
    )
    msgs = result["messages"]
    assert any(
        isinstance(m, SystemMessage) and "conversation summary" in str(m.content)
        for m in msgs
    )
    assert isinstance(msgs[-1], AIMessage)
    assert msgs[-1].content == "final"
    assert any(isinstance(m, SystemMessage) for m in bound.last_messages)
