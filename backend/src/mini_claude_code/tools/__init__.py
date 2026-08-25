"""Tool package: demo stubs, filesystem, shell, git, memory."""

from mini_claude_code.tools.default import build_default_tools
from mini_claude_code.tools.demo import add, demo_tools, get_agent_name
from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.git_tools import build_git_tools
from mini_claude_code.tools.memory_tools import build_memory_tools
from mini_claude_code.tools.path_jail import PathEscapeError, resolve_in_workspace
from mini_claude_code.tools.shell import build_shell_tools, command_is_denied

__all__ = [
    "PathEscapeError",
    "add",
    "build_coding_tools",
    "build_default_tools",
    "build_git_tools",
    "build_memory_tools",
    "build_shell_tools",
    "command_is_denied",
    "demo_tools",
    "get_agent_name",
    "resolve_in_workspace",
]
