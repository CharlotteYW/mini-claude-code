"""Helpers to spawn the in-repo HTTP counter MCP for tests/demos (M29)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def http_counter_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/mcp"


def wait_for_port(host: str, port: int, *, timeout_sec: float = 15.0) -> None:
    deadline = time.time() + timeout_sec
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.1)
    raise TimeoutError(
        f"HTTP MCP server did not listen on {host}:{port} within {timeout_sec}s "
        f"(last={last_err})"
    )


@dataclass
class HttpCounterServer:
    host: str
    port: int
    process: subprocess.Popen[Any]

    @property
    def url(self) -> str:
        return http_counter_url(self.host, self.port)

    def connection(self) -> dict[str, Any]:
        return {
            "transport": "streamable_http",
            "url": self.url,
            "headers": {"X-MCC-Demo": "http-counter"},
        }

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def start_http_counter_server(
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    ready_timeout_sec: float = 20.0,
) -> HttpCounterServer:
    """Spawn ``python -m mini_claude_code.mcp_servers.http_counter`` as a child."""
    port = pick_free_port(host) if port is None else int(port)
    env = os.environ.copy()
    env["MCC_HTTP_MCP_HOST"] = host
    env["MCC_HTTP_MCP_PORT"] = str(port)
    # Ensure package import works from backend root or repo root.
    src_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = (
        f"{src_root}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(src_root)
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "mini_claude_code.mcp_servers.http_counter"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_port(host, port, timeout_sec=ready_timeout_sec)
    except Exception:
        out = ""
        try:
            if proc.stdout:
                proc.terminate()
                out = proc.stdout.read() or ""
        except Exception:  # noqa: BLE001
            pass
        proc.kill()
        raise RuntimeError(
            f"failed to start http_counter on {host}:{port}\n{out}"
        ) from None
    return HttpCounterServer(host=host, port=port, process=proc)
