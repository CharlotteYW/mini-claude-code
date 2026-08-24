"""Assemble the default agent tool list (FS + shell + git)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool

from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.git_tools import build_git_tools
from mini_claude_code.tools.shell import build_shell_tools


def build_default_tools(
    workspace_root: Path, *, shell_timeout_sec: int = 30
) -> list[BaseTool]:
    """Full default toolset for the coding agent (M3 FS + M4 shell/git)."""
    root = workspace_root.expanduser().resolve()
    return [
        *build_coding_tools(root),
        *build_shell_tools(root, timeout_sec=shell_timeout_sec),
        *build_git_tools(root),
    ]
