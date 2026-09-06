"""M24 integration: shell-hooks pack denies FORBIDDEN_M24; /pick helper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.hooks import apply_hooks, resolve_hook_registry
from mini_claude_code.agent.plugins import resolve_plugins
from mini_claude_code.agent.slash_commands import (
    dispatch_slash_input,
    resolve_pick_selection,
    slash_registry_from_plugins,
)
from mini_claude_code.config import Settings

pytestmark = pytest.mark.integration


def test_shell_hooks_pack_blocks_in_graph(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    settings = Settings(
        _env_file=None,
        plugins_enabled=True,
        workspace_root=str(ws),
        hook_shell_enabled=True,
        hook_shell_allowlist="",
        hooks_use_demo=False,
        hooks_config_path="",
        context_compact_threshold=0,
        shell_backend="host",
    )
    resolve_plugins(settings, workspace_root=ws, seed_examples=True)
    registry = resolve_hook_registry(settings, workspace_root=ws)
    assert registry.pre, "expected shell-hooks Pre handler when enabled"

    called: list[str] = []

    def run_shell(command: str) -> str:
        called.append(command)
        return f"ran:{command}"

    tools = apply_hooks(
        [StructuredTool.from_function(run_shell, name="run_shell", description="shell")],
        registry,
    )

    class _Caller(BaseChatModel):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        @property
        def _llm_type(self) -> str:
            return "fake-m24"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
            self._n += 1
            if self._n == 1:
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "run_shell",
                            "args": {"command": "echo FORBIDDEN_M24"},
                            "id": "c1",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                msg = AIMessage(content="blocked as expected")
            return ChatResult(generations=[ChatGeneration(message=msg)])

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001
            return self

    graph = build_agent_graph(
        settings=settings,
        llm=_Caller(),
        tools=tools,
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
        apply_tool_hooks=False,  # already wrapped
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="run forbidden")]},
        config={"configurable": {"thread_id": "m24"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert "HOOK_DENIED" in str(tool_msgs[0].content)
    assert called == []


def test_pick_resolves_without_graph(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    packs = resolve_plugins(settings, workspace_root=ws, seed_examples=True)
    registry = slash_registry_from_plugins(packs)
    d = dispatch_slash_input("/pick", registry, plugins=packs)
    assert d.kind == "pick"
    assert d.pick_choices
    # Pick first entry by number
    expanded = resolve_pick_selection(registry, "1")
    assert isinstance(expanded, str) and len(expanded) > 10
