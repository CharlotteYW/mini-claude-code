"""MCP client → LangChain tools (M14 / M22 / M29).

Call chain (teaching):
  MCP_CONFIG / path / demo → MultiServerMCPClient → adapter BaseTool list
  → merge into build_default_tools → M9 apply_permissions → ToolNode

**M22:** prefer ``graph.ainvoke`` / ``astream`` so MCP tools use native
``ainvoke`` (no nested ``asyncio.run``). Sync ``invoke`` still works via an
optional ``func`` shim on prepared MCP tools.

**M14 cold path:** ``get_tools()`` often opens a **new session per tool call**
(stdio spawn) — fine for echo/add.

**M29 sticky path:** Streamable HTTP connections use ``client.session(...)``
on a dedicated loop so stateful tools (counter) accumulate across calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool

from mini_claude_code.config import Settings, get_settings

logger = logging.getLogger(__name__)


def echo_math_server_script() -> Path:
    """Absolute path to the in-repo stdio demo server."""
    return Path(__file__).resolve().parents[1] / "mcp_servers" / "echo_math.py"


def fake_docs_server_script() -> Path:
    """Absolute path to the M26 fake docs MCP server."""
    return Path(__file__).resolve().parents[1] / "mcp_servers" / "fake_docs.py"


def http_counter_server_script() -> Path:
    """Absolute path to the M29 Streamable HTTP counter server."""
    return Path(__file__).resolve().parents[1] / "mcp_servers" / "http_counter.py"


def default_demo_connections() -> dict[str, dict[str, Any]]:
    """Stdio connection dict for the packaged echo_math server."""
    return {
        "echo_math": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(echo_math_server_script())],
        }
    }


def fake_docs_connections() -> dict[str, dict[str, Any]]:
    """Stdio connection for fake_docs (content-policy teaching server)."""
    return {
        "fake_docs": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(fake_docs_server_script())],
        }
    }


def default_http_demo_connections(
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """HTTP connection for the in-repo http_counter server (must already be up)."""
    settings = settings or get_settings()
    url = settings.mcp_http_demo_url.strip() or "http://127.0.0.1:8765/mcp"
    headers = {"X-MCC-Demo": "http-counter"}
    return {
        "http_counter": {
            "transport": "streamable_http",
            "url": url,
            "headers": headers,
        }
    }


def parse_mcp_connections_json(raw: str) -> dict[str, dict[str, Any]]:
    """Parse MCP_CONFIG JSON. Empty / whitespace → {}."""
    text = raw.strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("MCP_CONFIG must be a JSON object of server_name → connection")
    out: dict[str, dict[str, Any]] = {}
    for name, conn in data.items():
        if not isinstance(conn, dict):
            raise ValueError(f"MCP server {name!r} connection must be an object")
        out[str(name)] = dict(conn)
    return out


def load_mcp_connections_file(path: Path) -> dict[str, dict[str, Any]]:
    """Load connections from a JSON file (YAML not required for M14)."""
    text = path.read_text(encoding="utf-8")
    return parse_mcp_connections_json(text)


def resolve_mcp_connections(
    settings: Settings | None = None,
    *,
    plugins: list[Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve opt-in MCP servers from settings, then merge plugin MCP (M23).

    Priority for *base*: ``MCP_CONFIG_PATH`` > ``MCP_CONFIG`` > demo flags.
    Demo flags: ``MCP_USE_DEMO`` (echo_math), ``MCP_USE_FAKE_DOCS`` (M26),
    and/or ``MCP_USE_HTTP_DEMO`` (M29 http_counter — server must be running).
    Plugin ``mcp:`` entries are unioned afterward; duplicate server name → error.
    Empty / all off / no plugins → {} (no MCP tools).
    """
    settings = settings or get_settings()
    path_raw = settings.mcp_config_path.strip()
    if path_raw:
        base = load_mcp_connections_file(Path(path_raw).expanduser().resolve())
    else:
        inline = settings.mcp_config.strip()
        if inline:
            base = parse_mcp_connections_json(inline)
        else:
            base = {}
            if settings.mcp_use_demo:
                base.update(default_demo_connections())
            if settings.mcp_use_fake_docs:
                base.update(fake_docs_connections())
            if settings.mcp_use_http_demo:
                base.update(default_http_demo_connections(settings))

    if not plugins:
        return base

    from mini_claude_code.agent.plugins import merge_mcp_connections

    return merge_mcp_connections(base, plugins)


def merge_tools_reject_collisions(
    builtin: list[BaseTool],
    mcp_tools: list[BaseTool],
) -> list[BaseTool]:
    """Append MCP tools; skip any whose name already exists in builtin.

    Collision policy (documented): **reject MCP duplicate** (keep builtin).
    Prefer renaming the MCP server tool over silently shadowing ``read_file``.
    """
    names = {t.name for t in builtin}
    merged = list(builtin)
    for tool in mcp_tools:
        if tool.name in names:
            logger.warning(
                "Skipping MCP tool %r: name collides with an existing tool",
                tool.name,
            )
            continue
        merged.append(tool)
        names.add(tool.name)
    return merged


def _normalize_mcp_result(result: Any) -> Any:
    """Flatten MCP text content blocks to a string when possible.

    Adapter ``ainvoke`` often returns ``[{type, text, ...}, ...]``; our sync
    ToolNode / permissions path prefers a plain ToolMessage string.
    """
    if isinstance(result, list) and result:
        texts: list[str] = []
        for block in result:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text", "")))
            elif hasattr(block, "text"):
                texts.append(str(block.text))
            else:
                return result
        if texts:
            return texts[0] if len(texts) == 1 else "\n".join(texts)
    return result


def wrap_mcp_tool_for_sync(tool: BaseTool) -> BaseTool:
    """Prepare an MCP adapter tool for sync *and* async graph paths (M14/M22).

    Always attaches ``coroutine`` (native ``ainvoke`` — no event-loop nesting).
    Also attaches ``func`` via ``asyncio.run`` as a **sync shim** for
    ``graph.invoke`` / tests. Prefer ``graph.ainvoke`` / ``astream`` so ToolNode
    uses ``coroutine`` and never calls ``asyncio.run``.
    """
    from langchain_core.tools import StructuredTool

    if getattr(tool, "_mcc_mcp_prepared", False):
        return tool

    async def _acall(**kwargs: Any) -> Any:
        return _normalize_mcp_result(await tool.ainvoke(kwargs))

    def _call(**kwargs: Any) -> Any:
        return asyncio.run(_acall(**kwargs))

    prepared = StructuredTool(
        name=tool.name,
        description=tool.description or tool.name,
        args_schema=getattr(tool, "args_schema", None),
        func=_call,
        coroutine=_acall,
    )
    prepared._mcc_mcp_prepared = True  # type: ignore[attr-defined]
    prepared._mcc_mcp_sync_shim = True  # type: ignore[attr-defined]
    return prepared


def prepare_mcp_tool_async_only(tool: BaseTool) -> BaseTool:
    """MCP tool with coroutine only — for async-first graphs (no asyncio.run shim)."""
    from langchain_core.tools import StructuredTool

    if getattr(tool, "_mcc_mcp_prepared", False) and not getattr(
        tool, "_mcc_mcp_sync_shim", True
    ):
        return tool

    async def _acall(**kwargs: Any) -> Any:
        return _normalize_mcp_result(await tool.ainvoke(kwargs))

    prepared = StructuredTool(
        name=tool.name,
        description=tool.description or tool.name,
        args_schema=getattr(tool, "args_schema", None),
        coroutine=_acall,
    )
    prepared._mcc_mcp_prepared = True  # type: ignore[attr-defined]
    prepared._mcc_mcp_sync_shim = False  # type: ignore[attr-defined]
    return prepared


async def load_mcp_tools_async(
    connections: dict[str, dict[str, Any]],
    *,
    sync_shim: bool = True,
) -> list[BaseTool]:
    """Discover tools from MCP servers via langchain-mcp-adapters.

    Stdio (and non-HTTP) → cold ``get_tools()``.
    HTTP → sticky ``client.session`` (M29).
    """
    if not connections:
        return []
    from mini_claude_code.tools.mcp_sticky import (
        load_sticky_http_tools,
        partition_mcp_connections,
    )

    cold, sticky = partition_mcp_connections(connections)
    loaded: list[BaseTool] = []

    if cold:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(cold)
        raw = list(await client.get_tools())
        if sync_shim:
            loaded.extend(wrap_mcp_tool_for_sync(t) for t in raw)
        else:
            loaded.extend(prepare_mcp_tool_async_only(t) for t in raw)

    if sticky:
        # Sticky runtime owns its loop/thread; start is sync-safe.
        loaded.extend(load_sticky_http_tools(sticky, sync_shim=sync_shim))

    return loaded


def load_mcp_tools_sync(
    connections: dict[str, dict[str, Any]] | None = None,
    *,
    settings: Settings | None = None,
    sync_shim: bool = True,
) -> list[BaseTool]:
    """Sync wrapper for graph build. Empty connections → [].

    When called from an already-running event loop (default async CLI holding
    ``AsyncPostgresSaver``), ``asyncio.run`` is illegal — load in a worker
    thread with its own loop instead.
    """
    conns = (
        connections
        if connections is not None
        else resolve_mcp_connections(settings)
    )
    if not conns:
        return []

    async def _load() -> list[BaseTool]:
        return await load_mcp_tools_async(conns, sync_shim=sync_shim)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_load())

    # Nested run forbidden; MCP stdio client needs its own loop in a thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_load())).result()
