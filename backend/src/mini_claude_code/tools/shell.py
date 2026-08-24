"""Host subprocess shell tool (M4).

IMPORTANT (learning): fixing cwd to WORKSPACE_ROOT is NOT a sandbox. A command
can still read/write paths outside the workspace (e.g. `cat /etc/passwd`).
The denylist below is a thin teaching brake — production needs containers
(M11), allowlists, and/or OS-level isolation.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

MAX_OUTPUT_CHARS = 20_000

# Best-effort string checks only — trivial to bypass. Do not treat as security.
_DENIED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+/", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r":\(\)\s*\{", re.I),  # fork bomb
    re.compile(r"\bshutdown\b", re.I),
    re.compile(r"\breboot\b", re.I),
    re.compile(r"\bdiskutil\s+erase", re.I),
]


def command_is_denied(command: str) -> str | None:
    """Return a reason if the command matches the thin denylist, else None."""
    for pattern in _DENIED_PATTERNS:
        if pattern.search(command):
            return f"command denied by policy (matched {pattern.pattern})"
    return None


def build_shell_tools(
    workspace_root: Path, *, timeout_sec: int = 30
) -> list[BaseTool]:
    root = workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    timeout = max(1, timeout_sec)

    def run_shell(command: str) -> str:
        """Run a shell command with cwd=workspace. Host subprocess — not sandboxed."""
        if not command or not command.strip():
            return "ERROR: command must be non-empty"
        denied = command_is_denied(command)
        if denied:
            return f"ERROR: {denied}"
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: timed out after {timeout}s"
        except OSError as exc:
            return f"ERROR: {exc}"

        chunks = [
            f"exit_code={completed.returncode}",
            f"cwd={root}",
        ]
        if completed.stdout:
            chunks.append("stdout:\n" + completed.stdout)
        if completed.stderr:
            chunks.append("stderr:\n" + completed.stderr)
        text = "\n".join(chunks)
        if len(text) > MAX_OUTPUT_CHARS:
            return text[:MAX_OUTPUT_CHARS] + f"\n... truncated after {MAX_OUTPUT_CHARS} chars"
        return text

    return [
        StructuredTool.from_function(
            run_shell,
            name="run_shell",
            description=(
                "Run a shell command with working directory fixed to the workspace. "
                "NOT a security sandbox — prefer dedicated git_* tools for git. "
                "Use for tests, formatters, and simple commands."
            ),
        )
    ]
