"""M31 integration: Postgres checkpoint list + fork (skip if Postgres down)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from mini_claude_code.agent.checkpointer import open_checkpointer
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.time_travel import (
    fork_from_checkpoint,
    list_checkpoints,
)
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


class _EchoBound:
    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        last = messages[-1]
        content = getattr(last, "content", str(last))
        return AIMessage(content=f"ack:{content}")


class _EchoLLM:
    def bind_tools(self, _tools: Any) -> _EchoBound:
        return _EchoBound()


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _postgres_or_skip(settings: Settings) -> None:
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")


def test_postgres_fork_leaves_source_tip() -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    source = f"m31-src-{uuid4().hex[:8]}"
    fork_tid = f"m31-fork-{uuid4().hex[:8]}"

    with open_checkpointer(settings, backend="postgres", setup=True) as cp:
        graph = build_agent_graph(
            llm=_EchoLLM(),
            tools=[],
            checkpointer=cp,
            apply_tool_permissions=False,
            apply_tool_hooks=False,
            settings=settings,
        )
        cfg = {"configurable": {"thread_id": source}, "recursion_limit": 10}
        graph.invoke({"messages": [HumanMessage(content="one")]}, cfg)
        graph.invoke({"messages": [HumanMessage(content="two")]}, cfg)
        tip_n = len(graph.get_state(cfg).values["messages"])

        rows = list_checkpoints(graph, source, completed_only=True)
        assert len(rows) >= 2
        earlier = min(rows, key=lambda r: r.message_count)

        fork_cfg = fork_from_checkpoint(
            graph,
            source_thread_id=source,
            checkpoint_id=earlier.checkpoint_id,
            target_thread_id=fork_tid,
        )
        assert fork_cfg["configurable"]["thread_id"] == fork_tid
        assert len(graph.get_state(fork_cfg).values["messages"]) == earlier.message_count
        assert len(graph.get_state(cfg).values["messages"]) == tip_n
