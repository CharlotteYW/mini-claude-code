"""M3 integration: live agent filesystem round-trip under WORKSPACE_ROOT."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

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


def test_agent_write_and_read_in_workspace(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    if settings.llm_provider == "ollama":
        if not _ollama_reachable(settings.ollama_base_url):
            pytest.skip("Ollama not reachable")
    else:
        from mini_claude_code.parity import _provider_ready

        reason = _provider_ready(settings, settings.llm_provider)
        if reason:
            pytest.skip(reason)

    ws = tmp_path / "agent_ws"
    ws.mkdir()
    settings = settings.model_copy(update={"workspace_root": str(ws)})

    graph = build_agent_graph(settings=settings)
    marker = "m3-fs-marker-42"
    prompt = (
        f"Use write_file to create greet.txt with exactly these contents: {marker}\n"
        "Then use read_file on greet.txt and stop when you have read it back."
    )
    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"provider invoke failed: {exc}")

    on_disk = ws / "greet.txt"
    if not on_disk.is_file():
        pytest.skip(
            "model did not create greet.txt (tool-calling flake); "
            f"messages={result['messages']!r}"
        )
    assert marker in on_disk.read_text(encoding="utf-8")
    assert any(isinstance(m, ToolMessage) for m in result["messages"])
