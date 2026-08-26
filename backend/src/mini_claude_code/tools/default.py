"""Assemble the default agent tool list (FS + shell + git + memory)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.git_tools import build_git_tools
from mini_claude_code.tools.memory_tools import build_memory_tools
from mini_claude_code.tools.shell import build_shell_tools


def build_default_tools(
    workspace_root: Path,
    *,
    shell_timeout_sec: int = 30,
    settings: Settings | None = None,
) -> list[BaseTool]:
    """Full default toolset: M3 FS + M4/M11 shell + git + M8 memory."""
    root = workspace_root.expanduser().resolve()
    settings = settings or get_settings()
    return [
        *build_coding_tools(root),
        *build_shell_tools(
            root,
            timeout_sec=shell_timeout_sec,
            backend=settings.shell_backend,  # type: ignore[arg-type]
            docker_image=settings.shell_docker_image,
            docker_network=settings.shell_docker_network,
        ),
        *build_git_tools(root),
        *build_memory_tools(settings),
    ]
