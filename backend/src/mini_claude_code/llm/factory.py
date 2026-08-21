"""LLM provider factory.

Learning point (deepened in M1): provider != model != wire protocol.

- anthropic  -> Anthropic Messages API (tool_use blocks; different from OpenAI)
- openai     -> OpenAI Chat Completions + tools
- openrouter -> same OpenAI protocol, different base_url + key (gateway)
- ollama     -> local OpenAI-compatible-ish API with Ollama-specific quirks

LangChain chat models normalize toward AIMessage.tool_calls / ToolMessage, but
quirks still leak (schema strictness, parallel tools, Gemma thinking channels).
M0 only constructs the client; M1 probes tool-calling parity.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from mini_claude_code.config import ProviderName, Settings, get_settings


def create_chat_model(
    settings: Settings | None = None,
    *,
    provider: ProviderName | None = None,
    model: str | None = None,
) -> BaseChatModel:
    """Return a LangChain chat model for the configured (or overridden) provider."""
    settings = settings or get_settings()
    provider = provider or settings.llm_provider
    model_name = model or settings.llm_model

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model_name, base_url=settings.ollama_base_url)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not settings.anthropic_api_key:
            raise ValueError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY in the environment."
            )
        return ChatAnthropic(model=model_name, api_key=settings.anthropic_api_key)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not settings.openai_api_key:
            raise ValueError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY in the environment."
            )
        kwargs: dict = {"model": model_name, "api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        # OpenRouter is intentionally ChatOpenAI + gateway URL — not a fourth
        # wire protocol. Naming it as a provider documents the gateway pattern.
        if not settings.openrouter_api_key:
            raise ValueError(
                "LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY in the environment."
            )
        return ChatOpenAI(
            model=model_name,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.openrouter_http_referer,
                "X-Title": settings.openrouter_x_title,
            },
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}")
