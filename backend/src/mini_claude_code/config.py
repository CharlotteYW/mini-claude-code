"""Environment-backed settings.

Why pydantic-settings: typed, fail-fast config is clearer for a multi-provider
factory than scattering os.getenv across call sites. Agent code should depend
on Settings + create_chat_model(), never on a hardcoded vendor.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["ollama", "anthropic", "openai", "openrouter"]


class Settings(BaseSettings):
    # env_file paths are relative to cwd; scripts also source/.load repo-root .env.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_provider: ProviderName = Field(default="ollama", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemma4:31b", alias="LLM_MODEL")

    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_http_referer: str = Field(
        default="https://localhost", alias="OPENROUTER_HTTP_REFERER"
    )
    openrouter_x_title: str = Field(
        default="mini-claude-code", alias="OPENROUTER_X_TITLE"
    )

    database_url: str = Field(
        default="postgresql://mcc:mcc@localhost:5432/mini_claude_code",
        alias="DATABASE_URL",
    )
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="mini-claude-code", alias="NEO4J_PASSWORD")

    # Agent filesystem jail (M3). Empty → <repo>/workspace
    workspace_root: str = Field(default="", alias="WORKSPACE_ROOT")

    # Host shell timeout (M4). Not a sandbox.
    shell_timeout_sec: int = Field(default=30, alias="SHELL_TIMEOUT_SEC")


def repo_root() -> Path:
    """mini-claude-code repo root (…/backend/src/mini_claude_code → parents[3])."""
    return Path(__file__).resolve().parents[3]


def resolve_workspace_root(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if settings.workspace_root.strip():
        return Path(settings.workspace_root).expanduser().resolve()
    return (repo_root() / "workspace").resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
