"""Assemble the default agent tool list (FS + shell + git + memory + subagents + MCP)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.store.base import BaseStore

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.git_tools import build_git_tools
from mini_claude_code.tools.github_pr import build_github_pr_tools
from mini_claude_code.tools.mcp_loader import (
    load_mcp_tools_sync,
    merge_tools_reject_collisions,
    resolve_mcp_connections,
)
from mini_claude_code.tools.memory_tools import build_memory_tools
from mini_claude_code.tools.shell import build_shell_tools
from mini_claude_code.tools.ship import apply_ship_gate_to_tools, build_ship_tools


def build_default_tools(
    workspace_root: Path,
    *,
    shell_timeout_sec: int = 30,
    settings: Settings | None = None,
    llm: BaseChatModel | None = None,
    plan_mode: bool = False,
    store: BaseStore | None = None,
) -> list[BaseTool]:
    """Full default toolset including M12–M14 (+ M23 plugin plane merges).

    Agent imports are lazy so ``import mini_claude_code.tools`` does not cycle
    through ``agent.graph`` → ``tools`` while the tools package is still loading.
    Pass ``store`` (M30) to enable ``store_put`` / ``store_get``.
    """
    # Lazy: agent.skills / subagents / plugins pull agent.__init__ → graph → tools.
    from mini_claude_code.agent.plugins import (
        collect_plugin_skill_defs,
        collect_plugin_subagent_defs,
        resolve_plugins,
    )
    from mini_claude_code.agent.skills import build_skill_tools
    from mini_claude_code.agent.subagents import build_subagent_tools

    root = workspace_root.expanduser().resolve()
    settings = settings or get_settings()
    plugins = resolve_plugins(settings, workspace_root=root)
    extra_skills = collect_plugin_skill_defs(plugins) if plugins else {}
    extra_subagents = collect_plugin_subagent_defs(plugins) if plugins else {}

    ship_tools, ship_gate = build_ship_tools(root, settings=settings)
    pr_tools = apply_ship_gate_to_tools(
        build_github_pr_tools(root, settings=settings),
        ship_gate,
    )
    builtin: list[BaseTool] = [
        *build_coding_tools(root),
        *build_shell_tools(
            root,
            timeout_sec=shell_timeout_sec,
            backend=settings.shell_backend,  # type: ignore[arg-type]
            docker_image=settings.shell_docker_image,
            docker_network=settings.shell_docker_network,
        ),
        *build_git_tools(root),
        *ship_tools,
        *pr_tools,
        *build_memory_tools(settings, workspace_root=root, store=store),
        *build_subagent_tools(
            root,
            settings=settings,
            llm=llm,
            plan_mode=plan_mode,
            extra_subagents=extra_subagents or None,
        ),
        *build_skill_tools(root, extra_skills=extra_skills or None),
    ]
    # M26: screen builtin read_file results (defense in depth vs no-ai files).
    if settings.content_policy_enabled and settings.content_policy_wrap_builtin_read:
        from mini_claude_code.content_policy import apply_content_policy_wrap

        builtin = apply_content_policy_wrap(builtin, settings=settings)

    connections = resolve_mcp_connections(settings, plugins=plugins)
    if not connections:
        return builtin
    mcp_tools = load_mcp_tools_sync(connections, settings=settings)
    if settings.content_policy_enabled:
        from mini_claude_code.content_policy import apply_content_policy_wrap

        mcp_tools = apply_content_policy_wrap(mcp_tools, settings=settings)
    return merge_tools_reject_collisions(builtin, mcp_tools)
