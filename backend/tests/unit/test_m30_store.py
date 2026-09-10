"""M30 unit tests: Store namespace + InMemoryStore cross-thread KV."""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from mini_claude_code.agent.permissions import default_mode_for, resolve_permission
from mini_claude_code.agent.store import (
    namespace_prefix,
    resolve_store_backend,
    store_get_value,
    store_namespace,
    store_put_value,
)
from mini_claude_code.config import Settings
from mini_claude_code.tools.memory_tools import build_memory_tools

pytestmark = pytest.mark.unit


def test_store_namespace_ignores_thread_and_uses_project() -> None:
    settings = Settings(_env_file=None, store_project_id="demo-proj")
    ns = store_namespace(settings)
    assert ns == ("mcc", "project", "demo-proj")
    assert "thread" not in ns
    assert namespace_prefix(ns) == "mcc.project.demo-proj"


def test_resolve_store_backend() -> None:
    assert (
        resolve_store_backend(Settings(_env_file=None, store_backend="memory"))
        == "memory"
    )
    assert (
        resolve_store_backend(Settings(_env_file=None, store_backend="postgres"))
        == "postgres"
    )
    with pytest.raises(ValueError):
        resolve_store_backend(Settings(_env_file=None, store_backend="redis"))


def test_inmemory_store_put_get_across_thread_ids() -> None:
    """Same Store instance + namespace; different thread_ids are irrelevant."""
    settings = Settings(_env_file=None, store_project_id="unit")
    store = InMemoryStore()
    # Simulate two LangGraph configs that only differ by thread_id.
    thread_a = {"configurable": {"thread_id": "A"}}
    thread_b = {"configurable": {"thread_id": "B"}}
    assert thread_a != thread_b

    store_put_value(store, "package_manager", "uv", settings=settings)
    assert store_get_value(store, "package_manager", settings=settings) == "uv"
    assert store_get_value(store, "missing", settings=settings) is None


def test_store_tools_registered_and_permissions() -> None:
    settings = Settings(_env_file=None, store_project_id="tools")
    store = InMemoryStore()
    tools = build_memory_tools(
        settings, workspace_root=Path("/tmp"), store=store
    )
    names = {t.name for t in tools}
    assert "store_put" in names
    assert "store_get" in names
    assert default_mode_for("store_get") == "auto"
    assert default_mode_for("store_put") == "ask"
    assert resolve_permission("store_put", plan_mode=True) == "deny"
    assert resolve_permission("store_get", plan_mode=True) == "auto"

    put = next(t for t in tools if t.name == "store_put")
    get = next(t for t in tools if t.name == "store_get")
    assert "stored key=" in put.invoke({"key": "k1", "value": "hello"})
    assert get.invoke({"key": "k1"}) == "k1=hello"


def test_store_tools_absent_without_store() -> None:
    tools = build_memory_tools(
        Settings(_env_file=None), workspace_root=Path("/tmp"), store=None
    )
    names = {t.name for t in tools}
    assert "store_put" not in names
    assert "store_get" not in names


def test_graph_compile_accepts_store_without_checkpointer() -> None:
    from unittest.mock import MagicMock

    from langchain_core.messages import AIMessage

    from mini_claude_code.agent.graph import build_agent_graph

    store = InMemoryStore()
    llm = MagicMock()
    llm.bind_tools.return_value = MagicMock(
        invoke=MagicMock(return_value=AIMessage(content="ok"))
    )
    graph = build_agent_graph(
        llm=llm,
        tools=[],
        store=store,
        checkpointer=None,
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    assert graph is not None
    graph2 = build_agent_graph(
        llm=llm,
        tools=[],
        store=store,
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    assert graph2 is not None
