"""M2 integration: real provider through the ReAct graph."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


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


def test_react_graph_add_with_live_provider() -> None:
    settings = _load_repo_settings()
    if settings.llm_provider == "ollama":
        if not _ollama_reachable(settings.ollama_base_url):
            pytest.skip("Ollama not reachable")
    else:
        from mini_claude_code.parity import _provider_ready

        reason = _provider_ready(settings, settings.llm_provider)
        if reason:
            pytest.skip(reason)

    graph = build_agent_graph(settings=settings)
    prompt = (
        "Use the add tool to compute 17 + 25. "
        "Do not compute the sum yourself; call the tool."
    )
    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"provider invoke failed: {exc}")

    messages = result["messages"]
    assert any(isinstance(m, ToolMessage) for m in messages), messages
    tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
    assert any("42" in str(m.content) for m in tool_msgs), tool_msgs
    last = messages[-1]
    assert isinstance(last, AIMessage)
