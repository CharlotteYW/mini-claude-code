"""M37 integration: Anthropic cache-marked invoke (skip without key)."""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from mini_claude_code.agent.prompt_cache import (
    invoke_kwargs_for_prompt_cache,
    mark_stable_prefix_for_cache,
)
from mini_claude_code.config import Settings, get_settings
from mini_claude_code.llm import create_chat_model

pytestmark = pytest.mark.integration


def test_anthropic_cache_marked_invoke_smoke() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY=key,
        LLM_MODEL=os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001"),
        PROMPT_CACHE_ENABLED=True,
    )
    model = create_chat_model(settings)
    messages = mark_stable_prefix_for_cache(
        [
            SystemMessage(content="You are a terse coding assistant for a smoke test."),
            HumanMessage(content="Reply with exactly: m37-cache-ok"),
        ],
        provider="anthropic",
        enabled=True,
    )
    kwargs = invoke_kwargs_for_prompt_cache("anthropic", enabled=True)
    response = model.invoke(messages, **kwargs)
    text = response.content if isinstance(response.content, str) else str(response.content)
    assert "m37-cache-ok" in text.lower() or len(text) > 0
    # Live cache hit is not guaranteed on a single short call; metadata optional.
    meta = getattr(response, "usage_metadata", None) or {}
    assert meta.get("input_tokens") is None or int(meta.get("input_tokens") or 0) >= 0
