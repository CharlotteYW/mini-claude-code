"""M1 unit tests: demo tool + parity helpers with a fake LLM."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from mini_claude_code.config import Settings
from mini_claude_code.parity import (
    _normalize_tool_calls,
    _provider_ready,
    probe_provider,
)
from mini_claude_code.tools import add

pytestmark = pytest.mark.unit


def test_add_tool_deterministic() -> None:
    assert add.name == "add"
    assert add.invoke({"a": 17, "b": 25}) == 42


def test_provider_ready_skip_reasons(clean_settings: Settings) -> None:
    assert _provider_ready(clean_settings, "ollama") is None
    assert _provider_ready(clean_settings, "anthropic") == "ANTHROPIC_API_KEY not set"
    assert _provider_ready(clean_settings, "openai") == "OPENAI_API_KEY not set"
    assert (
        _provider_ready(clean_settings, "openrouter") == "OPENROUTER_API_KEY not set"
    )

    ready = clean_settings.model_copy(update={"anthropic_api_key": "sk-ant"})
    assert _provider_ready(ready, "anthropic") is None


def test_normalize_tool_calls() -> None:
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "add", "args": {"a": 1, "b": 2}, "id": "call-1", "type": "tool_call"}
        ],
    )
    assert _normalize_tool_calls(message) == [
        {"name": "add", "args": {"a": 1, "b": 2}, "id": "call-1"}
    ]


class _FakeBound:
    """Minimal bind_tools target: first turn tool call, second turn final text."""

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        has_tool_result = any(isinstance(m, ToolMessage) for m in messages)
        if has_tool_result:
            return AIMessage(content="The sum of 17 and 25 is 42.")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "add",
                    "args": {"a": 17, "b": 25},
                    "id": "fake-tool-1",
                    "type": "tool_call",
                }
            ],
        )


class _FakeLLM:
    def bind_tools(self, _tools: Any) -> _FakeBound:
        return _FakeBound()


def test_probe_provider_with_fake_llm_pass(clean_settings: Settings) -> None:
    # Missing cloud keys would SKIP without llm=; injection bypasses network.
    result = probe_provider(
        clean_settings,
        "anthropic",
        model="fake-model",
        llm=_FakeLLM(),
    )
    assert result.status == "PASS"
    assert result.tool_calls == [
        {"name": "add", "args": {"a": 17, "b": 25}, "id": "fake-tool-1"}
    ]
    assert "42" in result.detail
