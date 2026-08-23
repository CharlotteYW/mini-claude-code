"""Tool package: demo stubs (M1) + filesystem coding tools (M3)."""

from mini_claude_code.tools.demo import add, demo_tools, get_agent_name
from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.path_jail import PathEscapeError, resolve_in_workspace

__all__ = [
    "PathEscapeError",
    "add",
    "build_coding_tools",
    "demo_tools",
    "get_agent_name",
    "resolve_in_workspace",
]
