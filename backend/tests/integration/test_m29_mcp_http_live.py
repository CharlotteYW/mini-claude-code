"""M29 integration: sticky HTTP MCP counter accumulates across calls."""

from __future__ import annotations

import pytest
from langchain_mcp_adapters.client import MultiServerMCPClient

from mini_claude_code.tools.mcp_http_demo import start_http_counter_server
from mini_claude_code.tools.mcp_loader import load_mcp_tools_sync
from mini_claude_code.tools.mcp_sticky import reset_sticky_http_runtime_for_tests

pytestmark = pytest.mark.integration


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    if isinstance(value, list) and value:
        block = value[0]
        if isinstance(block, dict) and "text" in block:
            return int(str(block["text"]).strip())
        if hasattr(block, "text"):
            return int(str(block.text).strip())
    raise AssertionError(f"cannot parse counter value from {value!r}")


def test_sticky_http_counter_accumulates() -> None:
    reset_sticky_http_runtime_for_tests()
    server = start_http_counter_server()
    try:
        tools = load_mcp_tools_sync({"http_counter": server.connection()})
        by_name = {t.name: t for t in tools}
        assert "bump_counter" in by_name
        assert "get_counter" in by_name

        first = _as_int(by_name["bump_counter"].invoke({"delta": 1}))
        second = _as_int(by_name["bump_counter"].invoke({"delta": 1}))
        total = _as_int(by_name["get_counter"].invoke({}))
        assert first == 1
        assert second == 2
        assert total == 2
        assert getattr(by_name["bump_counter"], "_mcc_mcp_sticky", False) is True
    finally:
        reset_sticky_http_runtime_for_tests()
        server.stop()


def test_cold_get_tools_does_not_accumulate_across_calls() -> None:
    """Contrast: adapter get_tools() path → new session per call → counter resets."""
    server = start_http_counter_server()
    try:
        client = MultiServerMCPClient({"http_counter": server.connection()})

        async def _two_cold_bumps() -> tuple[int, int]:
            tools = await client.get_tools()
            bump = next(t for t in tools if t.name == "bump_counter")
            a = _as_int(await bump.ainvoke({"delta": 1}))
            b = _as_int(await bump.ainvoke({"delta": 1}))
            return a, b

        import asyncio

        a, b = asyncio.run(_two_cold_bumps())
        # Each cold call uses a fresh MCP session → both return 1.
        assert a == 1
        assert b == 1
    finally:
        server.stop()
