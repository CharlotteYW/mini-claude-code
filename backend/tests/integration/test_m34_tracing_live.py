"""M34 integration: LangSmith opt-in smoke (skip without creds)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.agent.tracing import (
    JsonlTraceHandler,
    attach_callbacks,
    enrich_run_config,
    tracing_status,
)
from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools import demo_tools

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


class _EchoLLM:
    def bind_tools(self, _tools):
        return self

    def invoke(self, messages, config=None):
        last = messages[-1]
        return AIMessage(content=f"ack:{getattr(last, 'content', last)}")


def test_local_jsonl_with_graph_smoke(tmp_path: Path) -> None:
    """Offline path: callbacks attach and graph still runs (no LangSmith)."""
    path = tmp_path / "m34.jsonl"
    handler = JsonlTraceHandler(path)
    config: dict = {"recursion_limit": DEFAULT_RECURSION_LIMIT}
    config = dict(enrich_run_config(config, run_name="m34-test"))
    config = dict(attach_callbacks(config, handler))
    graph = build_agent_graph(
        llm=_EchoLLM(),  # type: ignore[arg-type]
        tools=[],
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    graph.invoke({"messages": [HumanMessage(content="ping")]}, config)
    handler.close_run(status="ok")
    text = path.read_text()
    assert "run_start" in text
    assert "run_end" in text


def test_langsmith_env_smoke_optional() -> None:
    """When tracing env + key present, status reports active; skip otherwise."""
    _load_repo_settings()
    status = tracing_status()
    if not status.langsmith_active:
        pytest.skip(
            "LANGCHAIN_TRACING_V2 + LANGSMITH_API_KEY not set — LangSmith smoke skipped"
        )
    assert status.project
    # Do not call remote APIs here — env presence is enough for CI without quota.
    assert os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
