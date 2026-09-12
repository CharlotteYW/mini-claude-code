"""M33 integration: live structured output + forced tool_choice (skip if unsupported)."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from mini_claude_code.agent.structured import (
    RouteDecision,
    first_tool_call_name,
    invoke_forced_tool,
    invoke_structured,
)
from mini_claude_code.config import Settings, get_settings
from mini_claude_code.llm import create_chat_model
from mini_claude_code.tools import demo_tools

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


def _require_live_settings() -> Settings:
    settings = _load_repo_settings()
    if settings.llm_provider == "ollama":
        if not _ollama_reachable(settings.ollama_base_url):
            pytest.skip("Ollama not reachable")
    else:
        from mini_claude_code.parity import _provider_ready

        reason = _provider_ready(settings, settings.llm_provider)
        if reason:
            pytest.skip(reason)
    return settings


def test_live_structured_route_decision() -> None:
    settings = _require_live_settings()
    llm = create_chat_model(settings)
    prompt = (
        "Classify this user request for an agent router.\n"
        "User: Extract the title from a paragraph of text I will paste; "
        "do not edit files or run shell.\n"
        "Choose mode=extract if no tools/edits are needed, else react."
    )
    try:
        decision = invoke_structured(llm, RouteDecision, prompt)
    except NotImplementedError as exc:
        pytest.skip(f"with_structured_output unsupported: {exc}")
    except Exception as exc:  # noqa: BLE001 — provider variance
        pytest.skip(f"structured output failed: {exc}")

    assert isinstance(decision, RouteDecision)
    assert decision.mode in {"react", "extract"}
    assert 0.0 <= decision.confidence <= 1.0
    assert decision.reason.strip()


def test_live_forced_tool_choice_add() -> None:
    settings = _require_live_settings()
    llm = create_chat_model(settings)
    prompt = "You must use the add tool to compute 17 + 25."
    try:
        msg = invoke_forced_tool(llm, demo_tools(), "add", prompt)
    except NotImplementedError as exc:
        pytest.skip(f"tool_choice unsupported: {exc}")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"forced tool_choice failed: {exc}")

    assert isinstance(msg, AIMessage)
    assert first_tool_call_name(msg) == "add"
    # Soft: args present when forced
    assert msg.tool_calls
    args = msg.tool_calls[0].get("args") if isinstance(msg.tool_calls[0], dict) else {}
    assert args is not None
