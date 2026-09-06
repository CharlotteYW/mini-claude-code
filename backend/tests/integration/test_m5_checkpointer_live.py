"""M5 integration: Postgres checkpointer resume across connections."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from mini_claude_code.agent.checkpointer import open_async_checkpointer, open_checkpointer
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from pathlib import Path

    from dotenv import load_dotenv

    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


class _EchoBound:
    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        last = messages[-1]
        content = getattr(last, "content", str(last))
        return AIMessage(content=f"ack:{content}")


class _EchoLLM:
    def bind_tools(self, _tools: Any) -> _EchoBound:
        return _EchoBound()


def _postgres_or_skip(settings: Settings):
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")


def test_postgres_same_thread_resumes_across_connections() -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    thread_id = f"integ-m5-{uuid4()}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10,
    }

    with open_checkpointer(settings, backend="postgres", setup=True) as cp:
        graph = build_agent_graph(
            llm=_EchoLLM(), tools=[], checkpointer=cp
        )
        graph.invoke(
            {"messages": [HumanMessage(content="codeword ORANGE")]},
            config=config,
        )

    # Fresh connection / compiled graph — same thread_id must load history.
    with open_checkpointer(settings, backend="postgres", setup=False) as cp:
        graph = build_agent_graph(
            llm=_EchoLLM(), tools=[], checkpointer=cp
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content="what was the codeword?")]},
            config=config,
        )

    humans = [m for m in result["messages"] if isinstance(m, HumanMessage)]
    assert any("ORANGE" in str(m.content) for m in humans)


def test_postgres_different_threads_isolated() -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    t_a = f"integ-m5-a-{uuid4()}"
    t_b = f"integ-m5-b-{uuid4()}"

    with open_checkpointer(settings, backend="postgres", setup=True) as cp:
        graph = build_agent_graph(
            llm=_EchoLLM(), tools=[], checkpointer=cp
        )
        graph.invoke(
            {"messages": [HumanMessage(content="secret APPLE")]},
            config={
                "configurable": {"thread_id": t_a},
                "recursion_limit": 10,
            },
        )
        result_b = graph.invoke(
            {"messages": [HumanMessage(content="hello")]},
            config={
                "configurable": {"thread_id": t_b},
                "recursion_limit": 10,
            },
        )

    humans_b = [m for m in result_b["messages"] if isinstance(m, HumanMessage)]
    assert not any("APPLE" in str(m.content) for m in humans_b)
    assert any("hello" in str(m.content) for m in humans_b)


def test_async_postgres_ainvoke_resumes_across_connections() -> None:
    """Default CLI path: AsyncPostgresSaver + ainvoke (sync PostgresSaver fails aget)."""
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    thread_id = f"integ-m5-async-{uuid4()}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10,
    }

    async def _run() -> None:
        async with open_async_checkpointer(
            settings, backend="postgres", setup=True
        ) as cp:
            graph = build_agent_graph(
                llm=_EchoLLM(), tools=[], checkpointer=cp
            )
            await graph.ainvoke(
                {"messages": [HumanMessage(content="codeword ORANGE")]},
                config=config,
            )

        async with open_async_checkpointer(
            settings, backend="postgres", setup=False
        ) as cp:
            graph = build_agent_graph(
                llm=_EchoLLM(), tools=[], checkpointer=cp
            )
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="what was the codeword?")]},
                config=config,
            )

        humans = [m for m in result["messages"] if isinstance(m, HumanMessage)]
        assert any("ORANGE" in str(m.content) for m in humans)

    asyncio.run(_run())
