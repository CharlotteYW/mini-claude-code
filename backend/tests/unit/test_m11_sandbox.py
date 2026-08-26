"""M11 unit tests: docker argv builder, denylist, missing docker, host backend."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mini_claude_code.tools.sandbox_docker import (
    DEFAULT_WORKDIR,
    build_docker_run_argv,
    run_in_docker,
)
from mini_claude_code.tools.shell import build_shell_tools

pytestmark = pytest.mark.unit


def test_build_docker_run_argv_mount_and_network(tmp_path: Path) -> None:
    argv = build_docker_run_argv(
        workspace_root=tmp_path,
        command="echo hi",
        image="python:3.12-slim",
        network="none",
    )
    assert argv[0] == "docker"
    assert "--rm" in argv
    assert "--network" in argv
    assert "none" in argv
    assert f"{tmp_path.resolve()}:{DEFAULT_WORKDIR}" in argv
    assert "-w" in argv
    assert DEFAULT_WORKDIR in argv
    assert argv[-3:] == ["sh", "-c", "echo hi"]


def test_settings_shell_backend_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHELL_BACKEND", raising=False)
    monkeypatch.delenv("SHELL_DOCKER_NETWORK", raising=False)
    monkeypatch.delenv("SHELL_DOCKER_IMAGE", raising=False)
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()
    # Avoid picking up a repo .env that overrides — construct explicitly.
    from mini_claude_code.config import Settings

    s = Settings(
        llm_provider="ollama",
        llm_model="x",
    )
    assert s.shell_backend == "docker"
    assert s.shell_docker_network == "none"
    assert "python" in s.shell_docker_image
    get_settings.cache_clear()


def test_denylist_applies_before_docker(tmp_path: Path) -> None:
    tools = {
        t.name: t
        for t in build_shell_tools(tmp_path, backend="docker", docker_image="alpine")
    }
    out = tools["run_shell"].invoke({"command": "sudo echo x"})
    assert out.startswith("ERROR:")
    assert "denied" in out


def test_missing_docker_binary_clear_error(tmp_path: Path) -> None:
    with patch("mini_claude_code.tools.sandbox_docker.docker_available", return_value=False):
        out = run_in_docker(
            tmp_path,
            "echo hi",
            image="python:3.12-slim",
        )
    assert out.startswith("ERROR:")
    assert "docker binary not found" in out


def test_host_backend_still_works(tmp_path: Path) -> None:
    tools = {t.name: t for t in build_shell_tools(tmp_path, backend="host")}
    out = tools["run_shell"].invoke({"command": "echo m11-host"})
    assert "sandbox=host" in out
    assert "m11-host" in out
