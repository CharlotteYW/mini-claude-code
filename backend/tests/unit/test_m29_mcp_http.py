"""M29 unit tests: HTTP connection parse + sticky lifecycle (mocked)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mini_claude_code.agent.permissions import default_mode_for
from mini_claude_code.config import Settings
from mini_claude_code.tools.mcp_loader import (
    default_http_demo_connections,
    resolve_mcp_connections,
)
from mini_claude_code.tools.mcp_sticky import (
    StickyHttpMcpRuntime,
    normalize_http_connection,
    partition_mcp_connections,
    reset_sticky_http_runtime_for_tests,
)

pytestmark = pytest.mark.unit


def test_normalize_http_connection_requires_url() -> None:
    with pytest.raises(ValueError, match="url"):
        normalize_http_connection({"transport": "streamable_http"})


def test_normalize_http_aliases_to_streamable_http() -> None:
    out = normalize_http_connection(
        {"transport": "http", "url": "http://127.0.0.1:9/mcp"}
    )
    assert out["transport"] == "streamable_http"
    assert out["url"] == "http://127.0.0.1:9/mcp"


def test_partition_stdio_vs_http() -> None:
    cold, sticky = partition_mcp_connections(
        {
            "echo_math": {"transport": "stdio", "command": "python", "args": ["a.py"]},
            "http_counter": {
                "transport": "streamable_http",
                "url": "http://127.0.0.1:8765/mcp",
            },
        }
    )
    assert list(cold.keys()) == ["echo_math"]
    assert list(sticky.keys()) == ["http_counter"]
    assert sticky["http_counter"]["transport"] == "streamable_http"


def test_resolve_http_demo_flag() -> None:
    settings = Settings(
        _env_file=None,
        mcp_config="",
        mcp_config_path="",
        mcp_use_demo=False,
        mcp_use_fake_docs=False,
        mcp_use_http_demo=True,
        mcp_http_demo_url="http://127.0.0.1:9999/mcp",
    )
    conns = resolve_mcp_connections(settings)
    assert "http_counter" in conns
    assert conns["http_counter"]["url"] == "http://127.0.0.1:9999/mcp"
    assert conns["http_counter"]["headers"]["X-MCC-Demo"] == "http-counter"


def test_default_http_demo_connections_shape() -> None:
    settings = Settings(_env_file=None, mcp_http_demo_url="http://localhost:1/mcp")
    conns = default_http_demo_connections(settings)
    assert conns["http_counter"]["transport"] == "streamable_http"


def test_sticky_runtime_open_use_close_mocked() -> None:
    reset_sticky_http_runtime_for_tests()

    fake_tool = MagicMock()
    fake_tool.name = "bump_counter"
    fake_tool.description = "bump"
    fake_tool.args_schema = None

    async def fake_ainvoke(payload: dict[str, Any]) -> Any:
        return {"ok": True, **payload}

    fake_tool.ainvoke = fake_ainvoke

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)

    client = MagicMock()
    client.session = MagicMock(return_value=session_cm)

    with (
        patch(
            "langchain_mcp_adapters.client.MultiServerMCPClient",
            return_value=client,
        ),
        patch(
            "langchain_mcp_adapters.tools.load_mcp_tools",
            new=AsyncMock(return_value=[fake_tool]),
        ),
    ):
        runtime = StickyHttpMcpRuntime()
        tools = runtime.start(
            {
                "http_counter": {
                    "transport": "streamable_http",
                    "url": "http://127.0.0.1:8765/mcp",
                }
            }
        )
        assert len(tools) == 1
        assert tools[0].name == "bump_counter"
        assert getattr(tools[0], "_mcc_mcp_sticky", False) is True
        # sync bridge works
        out = tools[0].invoke({"delta": 1})
        assert out["ok"] is True
        runtime.close()

    reset_sticky_http_runtime_for_tests()


def test_http_demo_tools_are_read_safe() -> None:
    for name in ("bump_counter", "get_counter", "echo_http"):
        assert default_mode_for(name) == "auto"
