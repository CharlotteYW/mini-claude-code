"""M5 unit tests: MemorySaver resume + checkpointer factory helpers."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.checkpointer import (
    open_async_checkpointer,
    open_checkpointer,
    resolve_checkpoint_backend,
)
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


class _EchoBound:
    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        last = messages[-1]
        content = getattr(last, "content", str(last))
        return AIMessage(content=f"ack:{content}")


class _EchoLLM:
    def bind_tools(self, _tools: Any) -> _EchoBound:
        return _EchoBound()


def test_memory_checkpointer_resumes_second_turn() -> None:
    """Same thread_id: second invoke sees prior Human messages (in-process)."""
    checkpointer = MemorySaver()
    graph = build_agent_graph(
        llm=_EchoLLM(), tools=[], checkpointer=checkpointer
    )
    config = {
        "configurable": {"thread_id": "unit-m5-resume"},
        "recursion_limit": 10,
    }

    r1 = graph.invoke(
        {"messages": [HumanMessage(content="codeword ORANGE")]},
        config=config,
    )
    humans_1 = [m for m in r1["messages"] if isinstance(m, HumanMessage)]
    assert len(humans_1) == 1
    assert "ORANGE" in str(humans_1[0].content)

    r2 = graph.invoke(
        {"messages": [HumanMessage(content="what was the codeword?")]},
        config=config,
    )
    humans_2 = [m for m in r2["messages"] if isinstance(m, HumanMessage)]
    assert len(humans_2) >= 2
    assert any("ORANGE" in str(m.content) for m in humans_2)


def test_resolve_checkpoint_backend_default_and_override(
    clean_settings: Settings,
) -> None:
    assert resolve_checkpoint_backend(clean_settings) == "postgres"
    assert (
        resolve_checkpoint_backend(clean_settings, backend="memory") == "memory"
    )


def test_open_checkpointer_memory_yields_memory_saver(
    clean_settings: Settings,
) -> None:
    with open_checkpointer(clean_settings, backend="memory") as cp:
        assert isinstance(cp, MemorySaver)


def test_open_async_checkpointer_memory_yields_memory_saver(
    clean_settings: Settings,
) -> None:
    async def _run() -> None:
        async with open_async_checkpointer(clean_settings, backend="memory") as cp:
            assert isinstance(cp, MemorySaver)

    asyncio.run(_run())


def test_memory_ainvoke_resumes_second_turn() -> None:
    """Async path: same thread_id accumulates Human messages (M22 + checkpointer)."""
    checkpointer = MemorySaver()
    graph = build_agent_graph(
        llm=_EchoLLM(), tools=[], checkpointer=checkpointer
    )
    config = {
        "configurable": {"thread_id": "unit-m5-async-resume"},
        "recursion_limit": 10,
    }

    async def _run() -> None:
        r1 = await graph.ainvoke(
            {"messages": [HumanMessage(content="codeword ORANGE")]},
            config=config,
        )
        humans_1 = [m for m in r1["messages"] if isinstance(m, HumanMessage)]
        assert len(humans_1) == 1

        r2 = await graph.ainvoke(
            {"messages": [HumanMessage(content="what was the codeword?")]},
            config=config,
        )
        humans_2 = [m for m in r2["messages"] if isinstance(m, HumanMessage)]
        assert len(humans_2) >= 2
        assert any("ORANGE" in str(m.content) for m in humans_2)

    asyncio.run(_run())
