"""Docker ephemeral sandbox for ``run_shell`` (M11).

Per-command ``docker run --rm`` with the workspace bind-mounted. This is
isolation for arbitrary shell — not a multi-tenant production sandbox
(no gVisor, rootless hardening, or long-lived agent sidecar).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

MAX_OUTPUT_CHARS = 20_000
DEFAULT_WORKDIR = "/workspace"


def build_docker_run_argv(
    *,
    workspace_root: Path,
    command: str,
    image: str,
    network: str = "none",
    workdir: str = DEFAULT_WORKDIR,
) -> list[str]:
    """Pure argv builder — unit-tested without a Docker daemon."""
    root = workspace_root.expanduser().resolve()
    # Mount only the workspace; container workdir is the mount target.
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "-v",
        f"{root}:{workdir}",
        "-w",
        workdir,
        image,
        "sh",
        "-c",
        command,
    ]


def docker_available() -> bool:
    return shutil.which("docker") is not None


def run_in_docker(
    workspace_root: Path,
    command: str,
    *,
    image: str,
    network: str = "none",
    timeout_sec: int = 30,
) -> str:
    """Execute ``command`` inside an ephemeral container; return a tool-style report."""
    if not docker_available():
        return (
            "ERROR: docker binary not found on PATH. "
            "Install Docker or set SHELL_BACKEND=host (unsafe host subprocess)."
        )

    root = workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    timeout = max(1, timeout_sec)
    argv = build_docker_run_argv(
        workspace_root=root,
        command=command,
        image=image,
        network=network,
    )

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: docker sandbox timed out after {timeout}s"
    except OSError as exc:
        return f"ERROR: docker sandbox failed to start: {exc}"

    chunks = [
        f"exit_code={completed.returncode}",
        f"sandbox=docker",
        f"image={image}",
        f"network={network}",
        f"cwd={DEFAULT_WORKDIR}",
        f"host_mount={root}",
    ]
    if completed.stdout:
        chunks.append("stdout:\n" + completed.stdout)
    if completed.stderr:
        chunks.append("stderr:\n" + completed.stderr)
    text = "\n".join(chunks)
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... truncated after {MAX_OUTPUT_CHARS} chars"
    return text
