"""M14 unit tests: MCP config parse, merge collisions, permissions for MCP names."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import tool

from mini_claude_code.tools.mcp_loader import (
    default_demo_connections,
    merge_tools_reject_collisions,
    parse_mcp_connections_json,
    resolve_mcp_connections,
)
from mini_claude_code.agent.permissions import resolve_permission
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


def test_parse_empty_config() -> None:
    assert parse_mcp_connections_json("") == {}
    assert parse_mcp_connections_json("   ") == {}


def test_parse_valid_stdio_entry() -> None:
    raw = json.dumps(
        {
            "echo_math": {
                "transport": "stdio",
                "command": "python",
                "args": ["/tmp/echo_math.py"],
            }
        }
    )
    conns = parse_mcp_connections_json(raw)
    assert "echo_math" in conns
    assert conns["echo_math"]["transport"] == "stdio"
    assert conns["echo_math"]["args"] == ["/tmp/echo_math.py"]


def test_resolve_empty_settings_no_mcp() -> None:
    settings = Settings(
        _env_file=None,
        mcp_config="",
        mcp_config_path="",
        mcp_use_demo=False,
    )
    assert resolve_mcp_connections(settings) == {}


def test_resolve_use_demo() -> None:
    settings = Settings(_env_file=None, mcp_use_demo=True)
    conns = resolve_mcp_connections(settings)
    assert "echo_math" in conns
    assert conns["echo_math"]["transport"] == "stdio"
    assert Path(conns["echo_math"]["args"][0]).name == "echo_math.py"


def test_resolve_path_over_inline(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "from_file": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["a.py"],
                }
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        mcp_config_path=str(path),
        mcp_config=json.dumps(
            {
                "from_inline": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["b.py"],
                }
            }
        ),
        mcp_use_demo=True,
    )
    conns = resolve_mcp_connections(settings)
    assert list(conns.keys()) == ["from_file"]


def test_merge_rejects_name_collision() -> None:
    @tool
    def read_file(path: str) -> str:
        """Builtin stub."""
        return path

    @tool
    def echo(text: str) -> str:
        """MCP-like."""
        return text

    mcp_read = read_file  # same name as builtin
    # Build a second tool also named read_file via MagicMock-like rename is hard;
    # use two tools where MCP reuses read_file name by cloning metadata.
    mcp_clash = MagicMock()
    mcp_clash.name = "read_file"
    mcp_ok = echo

    merged = merge_tools_reject_collisions([read_file], [mcp_clash, mcp_ok])
    names = [t.name for t in merged]
    assert names.count("read_file") == 1
    assert "echo" in names


def test_load_mcp_tools_sync_calls_client_when_configured() -> None:
    from mini_claude_code.tools import mcp_loader as mod

    @tool
    def echo(text: str) -> str:
        """Echo."""
        return text

    fake_tools = [echo]
    conns = default_demo_connections()

    async def fake_load(connections: dict, *, sync_shim: bool = True) -> list:
        assert connections == conns
        assert sync_shim is True
        return fake_tools

    with patch.object(mod, "load_mcp_tools_async", side_effect=fake_load):
        out = mod.load_mcp_tools_sync(conns)
    assert out == fake_tools


def test_unknown_mcp_tool_permission_is_ask_not_auto() -> None:
    assert resolve_permission("some_external_mcp_tool", plan_mode=False) == "ask"
    assert resolve_permission("some_external_mcp_tool", plan_mode=True) == "deny"


def test_demo_mcp_names_are_read_safe_auto() -> None:
    assert resolve_permission("echo", plan_mode=False) == "auto"
    assert resolve_permission("add", plan_mode=False) == "auto"
