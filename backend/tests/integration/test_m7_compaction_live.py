"""M7 integration: live summarizer compaction (skip if provider down)."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


def _load_repo_settings(**overrides: object) -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    base = get_settings()
    data = base.model_dump()
    # Map field names used by Settings
    if "context_compact_threshold" in overrides:
        data["context_compact_threshold"] = overrides["context_compact_threshold"]
    if "context_keep_recent" in overrides:
        data["context_keep_recent"] = overrides["context_keep_recent"]
    return Settings(_env_file=None, **{
        "LLM_PROVIDER": data["llm_provider"],
        "LLM_MODEL": data["llm_model"],
        "OLLAMA_BASE_URL": data["ollama_base_url"],
        "ANTHROPIC_API_KEY": data["anthropic_api_key"],
        "OPENAI_API_KEY": data["openai_api_key"],
        "OPENAI_BASE_URL": data["openai_base_url"],
        "OPENROUTER_API_KEY": data["openrouter_api_key"],
        "OPENROUTER_BASE_URL": data["openrouter_base_url"],
        "DATABASE_URL": data["database_url"],
        "NEO4J_URI": data["neo4j_uri"],
        "NEO4J_USER": data["neo4j_user"],
        "NEO4J_PASSWORD": data["neo4j_password"],
        "WORKSPACE_ROOT": data["workspace_root"],
        "SHELL_TIMEOUT_SEC": data["shell_timeout_sec"],
        "CHECKPOINT_BACKEND": data["checkpoint_backend"],
        "CONTEXT_COMPACT_THRESHOLD": overrides.get(
            "context_compact_threshold", data["context_compact_threshold"]
        ),
        "CONTEXT_KEEP_RECENT": overrides.get(
            "context_keep_recent", data["context_keep_recent"]
        ),
    })


def _ollama_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/api/tags", timeout=2
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def test_live_compaction_with_low_threshold() -> None:
    probe = _load_repo_settings()
    if probe.llm_provider == "ollama":
        if not _ollama_reachable(probe.ollama_base_url):
            pytest.skip("Ollama not reachable")
    else:
        from mini_claude_code.parity import _provider_ready

        reason = _provider_ready(probe, probe.llm_provider)
        if reason:
            pytest.skip(reason)

    settings = _load_repo_settings(
        context_compact_threshold=120,
        context_keep_recent=2,
    )
    graph = build_agent_graph(settings=settings, tools=[])
    history = [
        HumanMessage(content=("Remember project codename ORBITAL. " * 40).strip()),
        AIMessage(content=("Noted ORBITAL. " * 40).strip()),
        HumanMessage(content=("More context filler. " * 40).strip()),
        AIMessage(content=("Acknowledged. " * 40).strip()),
        HumanMessage(content="What was the project codename? One word."),
    ]
    try:
        result = graph.invoke(
            {"messages": history},
            config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"provider failed: {exc}")

    messages = result["messages"]
    assert any(
        isinstance(m, SystemMessage) and "conversation summary" in str(m.content)
        for m in messages
    ), messages
    last = messages[-1]
    assert isinstance(last, AIMessage)
    assert last.content
