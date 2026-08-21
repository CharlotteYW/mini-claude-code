"""M0 unit tests: settings defaults and LLM factory branching."""

from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from mini_claude_code.config import Settings
from mini_claude_code.llm import create_chat_model

pytestmark = pytest.mark.unit


def test_settings_defaults(clean_settings: Settings) -> None:
    assert clean_settings.llm_provider == "ollama"
    assert clean_settings.llm_model == "gemma4:31b"


def test_create_chat_model_ollama(clean_settings: Settings) -> None:
    model = create_chat_model(
        clean_settings, provider="ollama", model="gemma4:31b"
    )
    assert isinstance(model, ChatOllama)
    assert model.model == "gemma4:31b"
    assert "11434" in (model.base_url or "")


@pytest.mark.parametrize(
    ("provider", "exc_match"),
    [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
    ],
)
def test_create_chat_model_requires_api_key(
    clean_settings: Settings, provider: str, exc_match: str
) -> None:
    with pytest.raises(ValueError, match=exc_match):
        create_chat_model(clean_settings, provider=provider, model="x")  # type: ignore[arg-type]


def test_create_chat_model_anthropic_with_key(clean_settings: Settings) -> None:
    settings = clean_settings.model_copy(
        update={"anthropic_api_key": "sk-ant-test"}
    )
    model = create_chat_model(
        settings, provider="anthropic", model="claude-sonnet-4-20250514"
    )
    assert isinstance(model, ChatAnthropic)


def test_create_chat_model_openai_with_key(clean_settings: Settings) -> None:
    settings = clean_settings.model_copy(update={"openai_api_key": "sk-test"})
    model = create_chat_model(settings, provider="openai", model="gpt-4.1-mini")
    assert isinstance(model, ChatOpenAI)


def test_create_chat_model_openrouter_uses_openai_client_and_gateway(
    clean_settings: Settings,
) -> None:
    settings = clean_settings.model_copy(
        update={
            "openrouter_api_key": "or-test",
            "openrouter_base_url": "https://openrouter.ai/api/v1",
        }
    )
    model = create_chat_model(
        settings, provider="openrouter", model="anthropic/claude-sonnet-4"
    )
    assert isinstance(model, ChatOpenAI)
    base = str(model.openai_api_base or model.base_url or "")
    assert "openrouter.ai" in base
