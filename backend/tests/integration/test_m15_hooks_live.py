"""M15 integration: hooks on compiled graph with fake LLM (no network)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.hooks import HookRegistry, demo_hook_registry
from mini_claude_code.agent.hook_demos import block_dangerous_shell, append_audit_marker
from mini_claude_code.config import Settings

pytestmark = pytest.mark.integration


class _FakeShellThenDone(BaseChatModel):
    """Call run_shell once with a forbidden command, then finish."""

    def __init__(self) -> None:
        super().__init__()
        self._n = 0

    @property
    def _llm_type(self) -> str:
        return "fake-m15-shell"

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
            msg = AIMessage(content="blocked by hook, stopping")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


class _FakeEchoThenDone(BaseChatModel):
    def __init__(self) -> None:
        super().__init__()
        self._n = 0

    @property
    def _llm_type(self) -> str:
        return "fake-m15-echo"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self._n += 1
        if self._n == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"text": "SECRET=abc hi"},
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


class _FakeFinalOnly(BaseChatModel):
    def __init__(self) -> None:
        super().__init__()

    @property
    def _llm_type(self) -> str:
        return "fake-m15-stop"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="final only"))]
        )

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="ollama",
        llm_model="x",
        workspace_root=str(tmp_path),
        context_compact_threshold=0,
        hooks_use_demo=False,
        agent_plan_mode=False,
    )


def test_graph_pre_hook_blocks_dangerous_shell(tmp_path) -> None:
    called: list[str] = []

    def run_shell(command: str) -> str:
        called.append(command)
        return "should-not-run"

    tools = [
        StructuredTool.from_function(
            run_shell, name="run_shell", description="shell"
        )
    ]
    registry = HookRegistry(pre=[block_dangerous_shell])
    graph = build_agent_graph(
        settings=_settings(tmp_path),
        llm=_FakeShellThenDone(),
        tools=tools,
        checkpointer=MemorySaver(),
        ask_callback=lambda *_: True,  # would allow if Pre did not deny
        hook_registry=registry,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="wipe disk")]},
        config={"configurable": {"thread_id": "m15-pre"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert "HOOK_DENIED" in str(tool_msgs[0].content)
    assert called == []


def test_graph_post_hook_audits_and_stop_fires(tmp_path) -> None:
    def echo(text: str) -> str:
        return text

    tools = [StructuredTool.from_function(echo, name="echo", description="echo")]
    stop_log: list[str] = []

    def capture_stop(ctx) -> None:  # noqa: ANN001
        stop_log.append(ctx.stop_content or "")

    from mini_claude_code.agent.hook_demos import redact_secret_pattern

    registry = HookRegistry(
        post=[redact_secret_pattern, append_audit_marker],
        stop=[capture_stop],
    )
    graph = build_agent_graph(
        settings=_settings(tmp_path),
        llm=_FakeEchoThenDone(),
        tools=tools,
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
        hook_registry=registry,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="echo secret")]},
        config={"configurable": {"thread_id": "m15-post"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    content = str(tool_msgs[0].content)
    assert "SECRET=***" in content
    assert "[hook:audited]" in content
    assert stop_log == ["done"]


def test_graph_stop_hook_on_final_only(tmp_path) -> None:
    stop_log: list[str] = []

    def capture_stop(ctx) -> None:  # noqa: ANN001
        stop_log.append(ctx.stop_content or "")

    registry = HookRegistry(stop=[capture_stop])
    graph = build_agent_graph(
        settings=_settings(tmp_path),
        llm=_FakeFinalOnly(),
        tools=[],
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
        hook_registry=registry,
    )
    graph.invoke(
        {"messages": [HumanMessage(content="hi")]},
        config={"configurable": {"thread_id": "m15-stop"}},
    )
    assert stop_log == ["final only"]


def test_demo_registry_non_empty() -> None:
    reg = demo_hook_registry()
    assert not reg.empty
    assert reg.pre and reg.post and reg.stop
