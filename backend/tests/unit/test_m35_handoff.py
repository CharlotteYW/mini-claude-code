"""M35 unit tests: handoff transitions, caps, message isolation."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from mini_claude_code.agent.handoff import (
    HandoffError,
    apply_handoff,
    build_handoff_graph,
    filter_messages_for_agent,
    initial_handoff_state,
    run_handoff_demo,
)

pytestmark = pytest.mark.unit


def test_apply_handoff_sets_active_and_count() -> None:
    upd = apply_handoff(
        active_agent="supervisor",
        target="researcher",
        reason="need facts",
        handoff_count=0,
        scratchpad="",
        note="look for dates",
        message_len=3,
    )
    assert upd["active_agent"] == "researcher"
    assert upd["handoff_count"] == 1
    assert "dates" in upd["scratchpad"]
    assert upd["turn_start_index"] == 3
    assert isinstance(upd["messages"][0], SystemMessage)


def test_apply_handoff_rejects_unknown_and_disallowed() -> None:
    with pytest.raises(HandoffError, match="unknown"):
        apply_handoff(
            active_agent="supervisor",
            target="nope",
            reason="x",
            handoff_count=0,
            scratchpad="",
        )
    with pytest.raises(HandoffError, match="cannot hand off"):
        apply_handoff(
            active_agent="researcher",
            target="writer",
            reason="skip supervisor",
            handoff_count=0,
            scratchpad="",
        )


def test_bounce_cap() -> None:
    with pytest.raises(HandoffError, match="cap"):
        apply_handoff(
            active_agent="supervisor",
            target="researcher",
            reason="again",
            handoff_count=4,
            scratchpad="",
            max_handoffs=4,
        )


def test_filter_hides_peer_tool_noise_from_specialist() -> None:
    state = initial_handoff_state("Summarize the launch date")
    state["active_agent"] = "writer"
    state["scratchpad"] = "launch=2024-01-01"
    state["turn_start_index"] = 2
    state["messages"] = [
        AIMessage(content="supervisor planning"),
        ToolMessage(content="PEER_TOOL_SECRET", tool_call_id="t1"),
        SystemMessage(content="[handoff] supervisor → writer: draft"),
        AIMessage(content="writer local"),
    ]
    view = filter_messages_for_agent(state)
    blob = " ".join(str(getattr(m, "content", "")) for m in view)
    assert "PEER_TOOL_SECRET" not in blob
    assert "launch=2024-01-01" in blob
    assert "writer local" in blob
    assert "User task" in blob


def test_supervisor_strips_tool_messages() -> None:
    state = initial_handoff_state("task")
    state["active_agent"] = "supervisor"
    state["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "handoff_to",
                    "args": {"agent": "researcher", "reason": "x"},
                    "id": "c1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="SECRET_TOOL_BODY", tool_call_id="c1"),
        AIMessage(content="back"),
    ]
    view = filter_messages_for_agent(state)
    blob = " ".join(str(getattr(m, "content", "")) for m in view)
    assert "SECRET_TOOL_BODY" not in blob
    assert "back" in blob


class _ScriptedLLM:
    """Emit a fixed sequence of AIMessages (tool calls then finish)."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self._i = 0

    def bind_tools(self, _tools: Any) -> Any:
        return self

    def invoke(self, _messages: Any, config: Any = None) -> AIMessage:
        if self._i >= len(self._responses):
            return AIMessage(content="(no more scripted responses)")
        msg = self._responses[self._i]
        self._i += 1
        return msg


def test_graph_handoff_and_finish_with_fake_llm() -> None:
    llm = _ScriptedLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "handoff_to",
                        "args": {
                            "agent": "researcher",
                            "reason": "gather",
                            "note": "found X",
                        },
                        "id": "h1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "handoff_to",
                        "args": {"agent": "supervisor", "reason": "done researching"},
                        "id": "h2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish",
                        "args": {"summary": "all good"},
                        "id": "f1",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    )
    out = run_handoff_demo(llm, "Find X and finish", max_handoffs=4)
    assert out["status"] == "done"
    assert out["handoff_count"] == 2
    assert "found X" in out["scratchpad"]
    finals = [
        m.content
        for m in out["messages"]
        if isinstance(m, AIMessage) and "[finish]" in str(m.content)
    ]
    assert finals and "all good" in finals[-1]


def test_graph_unknown_handoff_returns_error_tool_message() -> None:
    llm = _ScriptedLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "handoff_to",
                        "args": {"agent": "nope", "reason": "bad"},
                        "id": "bad",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="recovering without tools"),
        ]
    )
    graph = build_handoff_graph(llm, max_handoffs=4)
    out = graph.invoke(initial_handoff_state("task"), {"recursion_limit": 10})
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert "ERROR" in str(tool_msgs[0].content)
    assert out["active_agent"] == "supervisor"
