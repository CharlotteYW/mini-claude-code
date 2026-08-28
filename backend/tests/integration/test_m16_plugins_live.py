"""M16 integration: slash /review reaches fake LLM; plugin hooks merge."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.plugins import (
    load_plugin_manifest,
    plugin_examples_dir,
    build_slash_registry,
)
from mini_claude_code.agent.slash_commands import dispatch_slash_input
from mini_claude_code.config import Settings

pytestmark = pytest.mark.integration


class _CapturePromptLLM(BaseChatModel):
    def __init__(self) -> None:
        super().__init__()
        self._prompts: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "fake-m16"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        for m in messages:
            if isinstance(m, HumanMessage):
                self._prompts.append(str(m.content))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="ok"))]
        )

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


def test_slash_review_expanded_prompt_seen_by_model(tmp_path) -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    reg = build_slash_registry([pack])
    dispatch = dispatch_slash_input("/review security", reg, plugins=[pack])
    assert dispatch.kind == "invoke"
    llm = _CapturePromptLLM()
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        llm_model="x",
        workspace_root=str(tmp_path),
        context_compact_threshold=0,
        plugins_enabled=True,
    )
    graph = build_agent_graph(
        settings=settings,
        llm=llm,
        tools=[],
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
    )
    graph.invoke(
        {"messages": [HumanMessage(content=dispatch.prompt)]},
        config={"configurable": {"thread_id": "m16-int"}},
    )
    assert llm._prompts
    assert "structured review" in llm._prompts[-1].lower()
    assert "security" in llm._prompts[-1]


def test_plugin_hook_merged_blocks_shell_in_graph(tmp_path) -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    called: list[str] = []

    def run_shell(command: str) -> str:
        called.append(command)
        return "ran"

    tools = [
        StructuredTool.from_function(
            run_shell, name="run_shell", description="shell"
        )
    ]
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        llm_model="x",
        workspace_root=str(tmp_path),
        context_compact_threshold=0,
        plugins_enabled=True,
    )
    # Copy plugin into workspace so resolve_hook_registry merges hooks
    plug_dir = tmp_path / "plugins" / "review"
    plug_dir.mkdir(parents=True)
    src = plugin_examples_dir() / "review" / "plugin.yaml"
    (plug_dir / "plugin.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    class _ShellCaller(BaseChatModel):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        @property
        def _llm_type(self) -> str:
            return "fake-m16-shell"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
            self._n += 1
            if self._n == 1:
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "run_shell",
                            "args": {"command": "rm -rf /"},
                            "id": "c1",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                msg = AIMessage(content="done")
            return ChatResult(generations=[ChatGeneration(message=msg)])

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001
            return self

    graph = build_agent_graph(
        settings=settings,
        llm=_ShellCaller(),
        tools=tools,
        checkpointer=MemorySaver(),
        ask_callback=lambda *_: True,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="go")]},
        config={"configurable": {"thread_id": "m16-hook"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert "HOOK_DENIED" in str(tool_msgs[0].content)
    assert called == []
