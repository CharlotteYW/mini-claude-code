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

    # Elasticsearch full-text (M21). Local Compose; no auth in learning setup.
    elasticsearch_url: str = Field(
        default="http://localhost:9200", alias="ELASTICSEARCH_URL"
    )
    elasticsearch_index: str = Field(default="mcc_chunks", alias="ELASTICSEARCH_INDEX")

    # Agent filesystem jail (M3). Empty → <repo>/workspace
    workspace_root: str = Field(default="", alias="WORKSPACE_ROOT")

    # Host shell timeout (M4). Isolation is SHELL_BACKEND=docker (M11).
    shell_timeout_sec: int = Field(default=30, alias="SHELL_TIMEOUT_SEC")
    shell_backend: Literal["host", "docker"] = Field(
        default="docker", alias="SHELL_BACKEND"
    )
    shell_docker_image: str = Field(
        default="python:3.12-slim", alias="SHELL_DOCKER_IMAGE"
    )
    shell_docker_network: str = Field(
        default="none", alias="SHELL_DOCKER_NETWORK"
    )

    # Session durability (M5): postgres (default) or memory
    checkpoint_backend: str = Field(default="postgres", alias="CHECKPOINT_BACKEND")

    # LangGraph Store (M30): cross-thread KV (not the chat transcript).
    # Default memory for offline; set STORE_BACKEND=postgres to share across processes.
    store_backend: str = Field(default="memory", alias="STORE_BACKEND")
    store_project_id: str = Field(default="default", alias="STORE_PROJECT_ID")

    # Context compaction (M7). threshold<=0 disables. Tokens ≈ chars/4.
    context_compact_threshold: int = Field(
        default=6000, alias="CONTEXT_COMPACT_THRESHOLD"
    )
    context_keep_recent: int = Field(default=12, alias="CONTEXT_KEEP_RECENT")
    # Soft token budget (M37). <=0 disables. When both threshold and budget > 0,
    # compact fires at min(threshold, budget). See effective_compact_threshold.
    context_token_budget: int = Field(default=0, alias="CONTEXT_TOKEN_BUDGET")
    # Anthropic prompt-cache breakpoints (M37). No-op for ollama/openai/openrouter.
    prompt_cache_enabled: bool = Field(default=True, alias="PROMPT_CACHE_ENABLED")

    # Minimal semantic notes (M8-B). Requires an Ollama embedding model pulled locally.
    embedding_model: str = Field(
        default="nomic-embed-text", alias="EMBEDDING_MODEL"
    )
    embedding_dimensions: int = Field(default=768, alias="EMBEDDING_DIMENSIONS")

    # Plan Mode (M9): read-only policy override for mutating tools.
    agent_plan_mode: bool = Field(default=False, alias="AGENT_PLAN_MODE")

    # Tools fan-out (M32). Default parallel (ToolNode gather); false = serial A/B.
    # Batches that include any ask tool are always serialized (HITL safety).
    tool_parallel: bool = Field(default=True, alias="TOOL_PARALLEL")
    # Optional cap (sync thread pool / async semaphore). None/0 = unbounded.
    tool_max_concurrency: int = Field(default=0, alias="TOOL_MAX_CONCURRENCY")

    # MCP client (M14). Empty config + demo off → no MCP tools.
    # Priority: MCP_CONFIG_PATH > MCP_CONFIG (JSON) > MCP_USE_DEMO.
    mcp_config: str = Field(default="", alias="MCP_CONFIG")
    mcp_config_path: str = Field(default="", alias="MCP_CONFIG_PATH")
    mcp_use_demo: bool = Field(default=False, alias="MCP_USE_DEMO")
    # M26: in-repo fake docs MCP (list_docs / read_doc + server content policy).
    mcp_use_fake_docs: bool = Field(default=False, alias="MCP_USE_FAKE_DOCS")
    # M29: Streamable HTTP counter demo (server must already be listening).
    mcp_use_http_demo: bool = Field(default=False, alias="MCP_USE_HTTP_DEMO")
    mcp_http_demo_url: str = Field(
        default="http://127.0.0.1:8765/mcp", alias="MCP_HTTP_DEMO_URL"
    )

    # Content policy (M26): screen read results for no-ai / CONFIDENTIAL markers.
    content_policy_enabled: bool = Field(default=True, alias="CONTENT_POLICY_ENABLED")
    content_policy_markers: str = Field(
        default="no-ai,CONFIDENTIAL", alias="CONTENT_POLICY_MARKERS"
    )
    content_policy_wrap_builtin_read: bool = Field(
        default=True, alias="CONTENT_POLICY_WRAP_BUILTIN_READ"
    )

    # Lifecycle hooks (M15). Priority: HOOKS_CONFIG_PATH > workspace/hooks.yaml > HOOKS_USE_DEMO.
    hooks_config_path: str = Field(default="", alias="HOOKS_CONFIG_PATH")
    hooks_use_demo: bool = Field(default=False, alias="HOOKS_USE_DEMO")
    # M24: shell/script hook runners (deny-by-default).
    hook_shell_enabled: bool = Field(default=False, alias="HOOK_SHELL_ENABLED")
    hook_shell_allowlist: str = Field(default="", alias="HOOK_SHELL_ALLOWLIST")
    hook_shell_timeout_sec: float = Field(default=5.0, alias="HOOK_SHELL_TIMEOUT_SEC")

    # Plugin packs (M16). Scan workspace/plugins when enabled.
    plugins_enabled: bool = Field(default=True, alias="PLUGINS_ENABLED")

    # LLM reliability / observability (M17).
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_sec: float = Field(default=1.0, alias="LLM_RETRY_BACKOFF_SEC")
    usage_report: bool = Field(default=False, alias="USAGE_REPORT")

    # Traces (M34): LangSmith is env opt-in (LANGCHAIN_TRACING_V2 + LANGSMITH_API_KEY).
    # Optional local JSONL path for offline span dumps (CLI --trace-local overrides).
    trace_local_path: str = Field(default="", alias="MCC_TRACE_JSONL")

    # Slack channel adapter (M18).
    slack_client_id: str = Field(default="", alias="SLACK_CLIENT_ID")
    slack_client_secret: str = Field(default="", alias="SLACK_CLIENT_SECRET")
    slack_signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")
    slack_app_token: str = Field(default="", alias="SLACK_APP_TOKEN")
    slack_bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    slack_bot_user_id: str = Field(default="", alias="SLACK_BOT_USER_ID")
    slack_oauth_redirect_uri: str = Field(
        default="http://127.0.0.1:3917/slack/oauth/callback",
        alias="SLACK_OAUTH_REDIRECT_URI",
    )
    slack_oauth_port: int = Field(default=3917, alias="SLACK_OAUTH_PORT")
    slack_channel_allowlist: str = Field(default="", alias="SLACK_CHANNEL_ALLOWLIST")
    slack_installations_path: str = Field(default="", alias="SLACK_INSTALLATIONS_PATH")
    channel_plan_mode: bool = Field(default=True, alias="CHANNEL_PLAN_MODE")
    slack_progress_emoji: str = Field(default="eyes", alias="SLACK_PROGRESS_EMOJI")

    # GitHub PR tool (M18). Token only — no GitHub OAuth in this milestone.
    gh_token: str | None = Field(default=None, alias="GH_TOKEN")
    pr_dry_run: bool = Field(default=True, alias="PR_DRY_RUN")

    # Pre-ship quality gate (M19).
    ship_require_green: bool = Field(default=True, alias="SHIP_REQUIRE_GREEN")
    ship_max_fix_iters: int = Field(default=3, alias="SHIP_MAX_FIX_ITERS")
    ship_mode: str = Field(default="pr", alias="SHIP_MODE")


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
