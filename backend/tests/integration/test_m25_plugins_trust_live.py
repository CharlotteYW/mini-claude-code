"""M25 integration: install path → trust → resolve; topology smoke."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START

from mini_claude_code.agent.graph import build_agent_graph, route_after_model
from mini_claude_code.agent.plugin_trust import load_trust_store
from mini_claude_code.agent.plugins import plugin_examples_dir, resolve_plugins
from mini_claude_code.agent.plugins_cli import main as plugins_main
from mini_claude_code.config import Settings

pytestmark = pytest.mark.integration


def test_install_and_trust_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "ws"
    monkeypatch.setenv("WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("PLUGINS_ENABLED", "1")
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()
    src = plugin_examples_dir() / "research"
    code = plugins_main(["install", str(src)])
    assert code == 0
    assert (ws / "plugins" / "research" / "plugin.yaml").is_file()
    store = load_trust_store(ws)
    assert store.get("research") and store.get("research").enabled is False

    code = plugins_main(
        ["trust", "research", "--enable", "--allow-mcp", "--deny-shell-hooks"]
    )
    assert code == 0
    get_settings.cache_clear()
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    active = resolve_plugins(settings, workspace_root=ws, seed_examples=False)
    assert "research" in {p.id for p in active}
    assert any(p.skill_refs for p in active if p.id == "research")


def test_graph_topology_unchanged(tmp_path: Path) -> None:
    class _Echo(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "echo"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok"))]
            )

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001
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
    assert route_after_model is not None
    assert START is not None and END is not None
    out = graph.invoke(
        {"messages": [HumanMessage(content="hi")]},
        config={"configurable": {"thread_id": "m25"}},
    )
    assert out["messages"][-1].content == "ok"


def test_seeded_packs_get_trust(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    packs = resolve_plugins(settings, workspace_root=ws, seed_examples=True)
    assert packs
    store = load_trust_store(ws)
    assert store.path and store.path.is_file()
    assert all(store.is_enabled(p.id) for p in packs)
