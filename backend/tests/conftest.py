"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from mini_claude_code.config import Settings, get_settings


@pytest.fixture
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings without ambient .env / process secrets interfering."""
    for key in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "OLLAMA_BASE_URL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "DATABASE_URL",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "WORKSPACE_ROOT",
        "SHELL_TIMEOUT_SEC",
        "CHECKPOINT_BACKEND",
        "CONTEXT_COMPACT_THRESHOLD",
        "CONTEXT_KEEP_RECENT",
        "CONTEXT_TOKEN_BUDGET",
        "PROMPT_CACHE_ENABLED",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
    ):
        monkeypatch.delenv(key, raising=False)

    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    yield settings
    get_settings.cache_clear()
