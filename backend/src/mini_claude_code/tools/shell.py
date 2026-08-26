"""Shell tool with host or Docker execution backend (M4 + M11).

IMPORTANT (learning):
- Host mode: fixing cwd to WORKSPACE_ROOT is NOT a sandbox.
- Docker mode (M11): ephemeral ``docker run --rm`` with workspace bind-mounted.
The denylist is a thin teaching brake — not the main control in Docker mode.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.tools.sandbox_docker import run_in_docker

MAX_OUTPUT_CHARS = 20_000

ShellBackend = Literal["host", "docker"]

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


def _run_on_host(workspace_root: Path, command: str, *, timeout_sec: int) -> str:
    root = workspace_root.expanduser().resolve()
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: timed out after {timeout_sec}s"
    except OSError as exc:
        return f"ERROR: {exc}"

    chunks = [
        f"exit_code={completed.returncode}",
        f"sandbox=host",
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


def build_shell_tools(
    workspace_root: Path,
    *,
    timeout_sec: int = 30,
    backend: ShellBackend = "docker",
    docker_image: str = "python:3.12-slim",
    docker_network: str = "none",
) -> list[BaseTool]:
    """Build ``run_shell``. Default backend is Docker (M11); use ``host`` for tests."""
    root = workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    timeout = max(1, timeout_sec)
    be: ShellBackend = backend if backend in ("host", "docker") else "docker"

    def run_shell(command: str) -> str:
        """Run a shell command in the configured sandbox backend."""
        if not command or not command.strip():
            return "ERROR: command must be non-empty"
        denied = command_is_denied(command)
        if denied:
            return f"ERROR: {denied}"
        if be == "host":
            return _run_on_host(root, command, timeout_sec=timeout)
        return run_in_docker(
            root,
            command,
            image=docker_image,
            network=docker_network,
            timeout_sec=timeout,
        )

    desc = (
        "Run a shell command. "
        + (
            "Executes in an ephemeral Docker container with the workspace mounted "
            f"at /workspace (network={docker_network}). "
            if be == "docker"
            else "HOST subprocess with cwd=workspace — NOT a security sandbox. "
        )
        + "Prefer dedicated git_* tools for git."
    )

    return [
        StructuredTool.from_function(
            run_shell,
            name="run_shell",
            description=desc,
        )
    ]
