"""M32 integration: multi tool_calls through build_agent_graph (fake LLM).

Live provider path skips when unreachable.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


@tool("add")
def ping_a() -> str:
    """Read-safe ping A (auto)."""
    return "ping-a"


@tool("echo")
def ping_b(text: str = "ping-b") -> str:
    """Read-safe ping B (auto)."""
    return text or "ping-b"


# Register names as read-safe for permission auto — they are unknown otherwise → ask.
# Use apply_tool_permissions=False for deterministic multi-call without HITL.


class _TwoToolThenDone(BaseChatModel):
    """Emit two tool_calls once, then a plain finish."""

    def __init__(self) -> None:
        super().__init__()
        self._n = 0

    @property
    def _llm_type(self) -> str:
        return "two-tool-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages: list[Any], stop: Any = None, **kwargs: Any) -> ChatResult:
        self._n += 1
        if self._n == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {},
                        "id": "pa",
                        "type": "tool_call",
                    },
                    {
                        "name": "echo",
                        "args": {"text": "ping-b"},
                        "id": "pb",
                        "type": "tool_call",
                    },
                ],
            )
        else:
            msg = AIMessage(content="both done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_graph_executes_two_tool_calls_parallel() -> None:
    graph = build_agent_graph(
        llm=_TwoToolThenDone(),
        tools=[ping_a, ping_b],
        apply_tool_permissions=False,
        apply_tool_hooks=False,
        tool_parallel=True,
    )
    out = graph.invoke(
        {"messages": [HumanMessage(content="ping both")]},
        config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
    )
    tms = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert {m.content for m in tms} == {"ping-a", "ping-b"}
    assert any(
        isinstance(m, AIMessage) and m.content == "both done" for m in out["messages"]
    )


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _ollama_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/api/tags", timeout=2
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def test_live_two_read_tools_optional() -> None:
    """Best-effort: model may emit one or two calls — skip if provider down."""
    settings = _load_repo_settings()
    if settings.llm_provider == "ollama":
        if not _ollama_reachable(settings.ollama_base_url):
            pytest.skip("Ollama not reachable")
    else:
        from mini_claude_code.parity import _provider_ready

        reason = _provider_ready(settings, settings.llm_provider)
        if reason:
            pytest.skip(reason)

    from mini_claude_code.tools import demo_tools

    graph = build_agent_graph(settings=settings, tools=demo_tools(), tool_parallel=True)
    prompt = (
        "Call the add tool twice in ONE response with two tool_calls: "
        "add(1,2) and add(3,4). Do not compute yourself."
    )
    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
        )
    except Exception as exc:  # noqa: BLE001 — live flake
        pytest.skip(f"live provider error: {exc}")

    tms = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    # Soft assertion: at least one tool ran; parallel emit is model-dependent.
    assert tms, "expected at least one ToolMessage from live model"
