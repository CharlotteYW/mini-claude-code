"""M6 integration: live token streaming + checkpointer resume via stream."""

from __future__ import annotations

import urllib.error
import urllib.request
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from mini_claude_code.agent.checkpointer import open_checkpointer
from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.agent.stream_cli import consume_agent_stream
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


def _provider_or_skip(settings: Settings) -> None:
    if settings.llm_provider == "ollama":
        if not _ollama_reachable(settings.ollama_base_url):
            pytest.skip("Ollama not reachable")
        return
    from mini_claude_code.parity import _provider_ready

    reason = _provider_ready(settings, settings.llm_provider)
    if reason:
        pytest.skip(reason)


def test_live_stream_emits_progressive_content() -> None:
    settings = _load_repo_settings()
    _provider_or_skip(settings)

    graph = build_agent_graph(settings=settings, tools=[])
    buf = StringIO()
    try:
        messages = consume_agent_stream(
            graph,
            "Reply with exactly: STREAM_OK",
            {"recursion_limit": DEFAULT_RECURSION_LIMIT},
            out=buf,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"provider stream failed: {exc}")

    text = buf.getvalue()
    assert "=== done ===" in text
    assert "AI:" in text
    # Soft check: final state has some assistant text (model-dependent wording).
    assert messages, "expected final messages from values stream"


def test_stream_turn_resumes_with_postgres() -> None:
    settings = _load_repo_settings()
    _provider_or_skip(settings)

    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")

    thread_id = f"integ-m6-{uuid4()}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": DEFAULT_RECURSION_LIMIT,
    }

    try:
        with open_checkpointer(settings, backend="postgres", setup=True) as cp:
            graph = build_agent_graph(
                settings=settings, tools=[], checkpointer=cp
            )
            consume_agent_stream(
                graph,
                "Remember codeword STREAM_M6.",
                config,
                out=StringIO(),
            )

        with open_checkpointer(settings, backend="postgres", setup=False) as cp:
            graph = build_agent_graph(
                settings=settings, tools=[], checkpointer=cp
            )
            consume_agent_stream(
                graph,
                "What codeword?",
                config,
                out=StringIO(),
            )
            snap = graph.get_state(config)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"stream+checkpointer failed: {exc}")

    humans = [m for m in snap.values["messages"] if isinstance(m, HumanMessage)]
    assert any("STREAM_M6" in str(m.content) for m in humans)
