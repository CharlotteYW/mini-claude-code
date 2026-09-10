"""M31 unit tests: checkpoint list/fork helpers (MemorySaver)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.time_travel import (
    fork_from_checkpoint,
    format_checkpoint_table,
    list_checkpoints,
    parse_rewind_args,
    resolve_checkpoint_ref,
    snapshot_to_row,
)

pytestmark = pytest.mark.unit


class _EchoBound:
    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        last = messages[-1]
        content = getattr(last, "content", str(last))
        return AIMessage(content=f"ack:{content}")


class _EchoLLM:
    def bind_tools(self, _tools: Any) -> _EchoBound:
        return _EchoBound()


def _tiny_graph(checkpointer: MemorySaver):
    return build_agent_graph(
        llm=_EchoLLM(),
        tools=[],
        checkpointer=checkpointer,
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )


def test_parse_rewind_args() -> None:
    assert parse_rewind_args("/rewind") == ""
    assert parse_rewind_args("/rewind 2") == "2"
    assert parse_rewind_args("/rewind abc-def") == "abc-def"
    assert parse_rewind_args("/help") is None
    assert parse_rewind_args("rewind 1") is None


def test_resolve_checkpoint_ref_index_and_prefix() -> None:
    from mini_claude_code.agent.time_travel import CheckpointRow

    rows = [
        CheckpointRow(1, "aaa-111", "t", None, (), 4, "hi"),
        CheckpointRow(2, "bbb-222", "t", None, (), 2, "earlier"),
    ]
    assert resolve_checkpoint_ref(rows, "2").checkpoint_id == "bbb-222"
    assert resolve_checkpoint_ref(rows, "aaa-111").checkpoint_id == "aaa-111"
    assert resolve_checkpoint_ref(rows, "bbb").checkpoint_id == "bbb-222"
    with pytest.raises(ValueError, match="out of range"):
        resolve_checkpoint_ref(rows, "9")


def test_memory_fork_diverges_new_thread_source_tip_unchanged() -> None:
    checkpointer = MemorySaver()
    graph = _tiny_graph(checkpointer)
    source = "unit-m31-src"
    cfg = {"configurable": {"thread_id": source}, "recursion_limit": 10}

    graph.invoke({"messages": [HumanMessage(content="turn-one")]}, cfg)
    graph.invoke({"messages": [HumanMessage(content="turn-two-BAD")]}, cfg)

    tip_before = graph.get_state(cfg)
    assert len(tip_before.values["messages"]) >= 4

    rows = list_checkpoints(graph, source, completed_only=True)
    assert len(rows) >= 2
    table = format_checkpoint_table(rows)
    assert "checkpoint_id" in table

    # Oldest completed with fewer messages than tip (after first turn).
    earlier = min(rows, key=lambda r: r.message_count)
    assert earlier.message_count < rows[0].message_count

    fork_cfg = fork_from_checkpoint(
        graph,
        source_thread_id=source,
        checkpoint_id=earlier.checkpoint_id,
        target_thread_id="unit-m31-fork",
    )
    assert fork_cfg["configurable"]["thread_id"] == "unit-m31-fork"

    fork_state = graph.get_state(fork_cfg)
    assert len(fork_state.values["messages"]) == earlier.message_count

    # Source tip unchanged.
    tip_after = graph.get_state(cfg)
    assert len(tip_after.values["messages"]) == len(tip_before.values["messages"])

    # Divergent third turn on fork only.
    fork_tip = {"configurable": {"thread_id": "unit-m31-fork"}, "recursion_limit": 10}
    graph.invoke(
        {"messages": [HumanMessage(content="turn-three-GOOD")]},
        fork_tip,
    )
    assert len(graph.get_state(cfg).values["messages"]) == len(
        tip_before.values["messages"]
    )
    assert len(graph.get_state(fork_tip).values["messages"]) > earlier.message_count


def test_fork_rejects_same_thread_id() -> None:
    checkpointer = MemorySaver()
    graph = _tiny_graph(checkpointer)
    cfg = {"configurable": {"thread_id": "same"}, "recursion_limit": 10}
    graph.invoke({"messages": [HumanMessage(content="x")]}, cfg)
    rows = list_checkpoints(graph, "same", completed_only=True)
    with pytest.raises(ValueError, match="differ"):
        fork_from_checkpoint(
            graph,
            source_thread_id="same",
            checkpoint_id=rows[0].checkpoint_id,
            target_thread_id="same",
        )


def test_snapshot_to_row_preview() -> None:
    class _Snap:
        values = {"messages": [HumanMessage(content="hello world")]}
        next = ()
        config = {
            "configurable": {"thread_id": "t", "checkpoint_id": "cid-1"}
        }
        created_at = "2026-01-01"

    row = snapshot_to_row(1, _Snap())
    assert row.preview == "hello world"
    assert row.checkpoint_id == "cid-1"
