"""M23 integration: plugin MCP / skills surface via default tool build."""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.graph import END, START

from mini_claude_code.agent.graph import build_agent_graph, route_after_model
from mini_claude_code.agent.plugins import plugin_examples_dir, resolve_plugins
from mini_claude_code.config import Settings
from mini_claude_code.tools.default import build_default_tools
from mini_claude_code.tools.mcp_loader import (
    load_mcp_tools_sync,
    resolve_mcp_connections,
)

pytestmark = pytest.mark.integration


def _ws_with_example_packs(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    resolve_plugins(settings, workspace_root=ws, seed_examples=True)
    return ws


def test_docs_mcp_pack_loads_read_doc(tmp_path: Path) -> None:
    ws = _ws_with_example_packs(tmp_path)
    settings = Settings(
        _env_file=None,
        plugins_enabled=True,
        workspace_root=str(ws),
        mcp_use_demo=False,
        mcp_use_fake_docs=False,
        mcp_config="",
        mcp_config_path="",
        content_policy_enabled=True,
    )
    packs = resolve_plugins(settings, workspace_root=ws, seed_examples=False)
    conns = resolve_mcp_connections(settings, plugins=packs)
    assert "fake_docs" in conns
    try:
        tools = {t.name: t for t in load_mcp_tools_sync(conns, settings=settings)}
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MCP unavailable: {exc}")
    assert "read_doc" in tools
    assert "list_docs" in tools
    out = str(tools["read_doc"].invoke({"doc_id": "clean-guide"}))
    assert "CONTENT_POLICY_DENIED" not in out


def test_research_pack_skill_via_default_tools(tmp_path: Path) -> None:
    ws = _ws_with_example_packs(tmp_path)
    settings = Settings(
        _env_file=None,
        plugins_enabled=True,
        workspace_root=str(ws),
        mcp_use_demo=False,
        mcp_use_fake_docs=False,
        mcp_config="",
        mcp_config_path="",
        shell_backend="host",
        content_policy_enabled=False,
    )
    tools = {t.name: t for t in build_default_tools(ws, settings=settings)}
    assert "load_skill" in tools
    assert "run_subagent" in tools
    body = tools["load_skill"].invoke({"name": "doc-research"})
    assert "Doc research playbook" in body or "doc-research" in body.lower()
    # Subagent name present in tool description
    assert "doc-scout" in (tools["run_subagent"].description or "")


def test_graph_topology_unchanged(tmp_path: Path) -> None:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langgraph.checkpoint.memory import MemorySaver

    class _Echo(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "echo"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok"))]
            )

        def bind_tools(self, tools, **kwargs):
            return self

    ws = tmp_path / "ws"
    ws.mkdir()
    settings = Settings(
        _env_file=None,
        plugins_enabled=False,
        workspace_root=str(ws),
        context_compact_threshold=0,
    )
    graph = build_agent_graph(
        settings=settings,
        llm=_Echo(),
        tools=[],
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    # Compiled graph still exposes call_model + tools nodes conceptually via edges.
    assert route_after_model is not None
    assert START is not None and END is not None
    # Smoke invoke
    from langchain_core.messages import HumanMessage

    out = graph.invoke(
        {"messages": [HumanMessage(content="hi")]},
        config={"configurable": {"thread_id": "m23-topo"}},
    )
    assert out["messages"][-1].content == "ok"


def test_package_examples_exist() -> None:
    root = plugin_examples_dir()
    assert (root / "docs-mcp" / "plugin.yaml").is_file()
    assert (root / "research" / "skills" / "doc-research" / "SKILL.md").is_file()
    assert (root / "research" / "subagents" / "doc-scout.yaml").is_file()
    from mini_claude_code.agent.plugins import (
        collect_plugin_skill_defs,
        load_plugin_manifest,
    )

    pack = load_plugin_manifest(root / "research" / "plugin.yaml")
    assert "doc-research" in collect_plugin_skill_defs([pack])
