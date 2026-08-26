"""M11 integration: real Docker sandbox when daemon is available."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mini_claude_code.tools.sandbox_docker import docker_available, run_in_docker
from mini_claude_code.tools.shell import build_shell_tools

pytestmark = pytest.mark.integration


def _docker_daemon_ok() -> bool:
    if not docker_available():
        return False
    try:
        completed = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


requires_docker = pytest.mark.skipif(
    not _docker_daemon_ok(),
    reason="Docker daemon not available",
)


@requires_docker
def test_docker_echo_and_pwd(tmp_path: Path) -> None:
    tools = {
        t.name: t
        for t in build_shell_tools(
            tmp_path,
            backend="docker",
            docker_image="python:3.12-slim",
            docker_network="none",
            timeout_sec=120,
        )
    }
    out = tools["run_shell"].invoke({"command": "echo hello-m11 && pwd"})
    assert "sandbox=docker" in out
    assert "hello-m11" in out
    assert "/workspace" in out
    assert "exit_code=0" in out


@requires_docker
def test_host_file_outside_mount_not_visible(tmp_path: Path) -> None:
    """Sentinel lives next to workspace, not inside the bind mount."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sentinel = tmp_path / "secret-outside.txt"
    sentinel.write_text("TOPSECRET", encoding="utf-8")

    # Absolute path on the host — should not exist inside the container mount.
    host_path = str(sentinel.resolve())
    out = run_in_docker(
        workspace,
        f"if [ -f '{host_path}' ]; then echo LEAKED; else echo ISOLATED; fi",
        image="python:3.12-slim",
        network="none",
        timeout_sec=120,
    )
    assert "ISOLATED" in out
    assert "LEAKED" not in out
    assert "sandbox=docker" in out
