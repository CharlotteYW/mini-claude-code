"""In-repo Streamable HTTP MCP server (M29) — remote-shaped, stateful session.

Tools:
  - bump_counter(delta=1) → new value (proves sticky session)
  - get_counter() → current value
  - echo_http(text) → text (smoke)

Run (default 127.0.0.1:8765)::

    python -m mini_claude_code.mcp_servers.http_counter

Env overrides: ``MCC_HTTP_MCP_HOST``, ``MCC_HTTP_MCP_PORT``.

Simplification: localhost bind; no OAuth. ``stateless_http=False`` so the MCP
session keeps state. Counters are keyed by ``id(ctx.session)`` so cold
``get_tools()`` (new session per call) does not share sticky state.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import Context, FastMCP

# Per MCP server-session counters (not process-global).
_counters: dict[int, int] = {}


def _host() -> str:
    return os.environ.get("MCC_HTTP_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _port() -> int:
    raw = os.environ.get("MCC_HTTP_MCP_PORT", "8765").strip() or "8765"
    return int(raw)


def _session_key(ctx: Context) -> int:
    return id(ctx.session)


mcp = FastMCP(
    "http-counter",
    host=_host(),
    port=_port(),
    # Keep MCP sessions stateful so bump_counter accumulates per sticky client.
    stateless_http=False,
)


@mcp.tool()
def bump_counter(delta: int = 1, ctx: Context | None = None) -> int:
    """Add delta to this MCP session's counter and return the new value.

    Survives across tool calls only when the MCP *client* keeps a sticky
    session. Cold get_tools() (new session per call) starts from 0 again.
    """
    if ctx is None:
        raise RuntimeError("bump_counter requires MCP Context")
    key = _session_key(ctx)
    _counters[key] = _counters.get(key, 0) + int(delta)
    return _counters[key]


@mcp.tool()
def get_counter(ctx: Context | None = None) -> int:
    """Return the current counter for this MCP session."""
    if ctx is None:
        raise RuntimeError("get_counter requires MCP Context")
    return _counters.get(_session_key(ctx), 0)


@mcp.tool()
def echo_http(text: str) -> str:
    """Return the same text (HTTP transport smoke tool)."""
    return text


def main() -> None:
    print(
        f"http-counter MCP listening on "
        f"http://{mcp.settings.host}:{mcp.settings.port}/mcp "
        f"(streamable-http)",
        flush=True,
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
