"""M4 unit tests: shell denylist/timeout/cwd and git helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mini_claude_code.tools import (
    build_default_tools,
    build_git_tools,
    build_shell_tools,
    command_is_denied,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_command_is_denied_patterns() -> None:
    assert command_is_denied("sudo rm -rf /tmp/x") is not None
    assert command_is_denied("rm -rf /") is not None
    assert command_is_denied("echo hello") is None


def test_run_shell_echo_and_cwd(workspace: Path) -> None:
    tools = {t.name: t for t in build_shell_tools(workspace)}
    out = tools["run_shell"].invoke({"command": "echo hello-m4 && pwd"})
    assert "exit_code=0" in out
    assert "hello-m4" in out
    assert str(workspace.resolve()) in out


def test_run_shell_denies_sudo(workspace: Path) -> None:
    tools = {t.name: t for t in build_shell_tools(workspace)}
    out = tools["run_shell"].invoke({"command": "sudo echo nope"})
    assert out.startswith("ERROR:")
    assert "denied" in out


def test_run_shell_timeout(workspace: Path) -> None:
    tools = {t.name: t for t in build_shell_tools(workspace, timeout_sec=1)}
    out = tools["run_shell"].invoke({"command": "sleep 5"})
    assert "timed out" in out


def test_git_status_diff_log_commit(workspace: Path) -> None:
    _git_init(workspace)
    (workspace / "a.txt").write_text("one\n", encoding="utf-8")
    tools = {t.name: t for t in build_git_tools(workspace)}

    status = tools["git_status"].invoke({})
    assert "exit_code=0" in status
    assert "a.txt" in status

    commit = tools["git_commit"].invoke({"message": "add a.txt"})
    assert "exit_code=0" in commit

    log = tools["git_log"].invoke({"max_count": 3})
    assert "add a.txt" in log

    (workspace / "a.txt").write_text("two\n", encoding="utf-8")
    diff = tools["git_diff"].invoke({"staged": False})
    assert "exit_code=0" in diff
    assert "two" in diff or "+two" in diff


def test_default_tools_include_fs_shell_git(workspace: Path) -> None:
    names = {t.name for t in build_default_tools(workspace)}
    assert {"read_file", "run_shell", "git_status", "git_commit"} <= names
