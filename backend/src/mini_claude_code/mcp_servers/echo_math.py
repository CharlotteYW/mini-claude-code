"""Tiny stdio MCP server for M14 (no npx / no network).

Tools:
  - echo(text) → text
  - add(a, b) → a + b

Run: ``python -m mini_claude_code.mcp_servers.echo_math`` (stdio).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo-math")


@mcp.tool()
def echo(text: str) -> str:
    """Return the same text (MCP adapter smoke tool)."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


def main() -> None:
    # Default transport is stdio — required for MultiServerMCPClient spawn.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
