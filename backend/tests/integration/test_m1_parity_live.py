"""M1 integration: real provider tool-calling probes."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.parity import probe_provider

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _ollama_reachable(base_url: str) -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def test_ollama_tool_round_trip() -> None:
    settings = _load_repo_settings()
    if not _ollama_reachable(settings.ollama_base_url):
        pytest.skip("Ollama not reachable")
    result = probe_provider(settings, "ollama", round_trip=True)
    if result.status != "PASS":
        pytest.skip(f"Ollama probe not PASS: {result.detail}")
    assert result.tool_calls
    assert result.tool_calls[0]["name"] == "add"


@pytest.mark.parametrize(
    ("provider",),
    [("anthropic",), ("openai",), ("openrouter",)],
)
def test_cloud_provider_tool_probe_when_keyed(provider: str) -> None:
    from mini_claude_code.parity import _provider_ready

    settings = _load_repo_settings()
    reason = _provider_ready(settings, provider)  # type: ignore[arg-type]
    if reason:
        pytest.skip(reason)

    result = probe_provider(settings, provider, round_trip=True)  # type: ignore[arg-type]
    if result.status == "SKIP":
        pytest.skip(result.detail)
    assert result.status == "PASS", result.detail
    assert result.tool_calls
    assert result.tool_calls[0]["name"] == "add"
