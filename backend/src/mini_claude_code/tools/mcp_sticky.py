"""Sticky MCP HTTP sessions (M29).

``MultiServerMCPClient.get_tools()`` opens a **new** session per tool call.
For Streamable HTTP demos we keep one ``client.session(...)`` alive on a
dedicated asyncio loop/thread so stateful tools (e.g. bump_counter) accumulate.

Stdio connections stay on the cold ``get_tools`` path (M14 teaching baseline).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import AsyncExitStack
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

logger = logging.getLogger(__name__)

_HTTP_TRANSPORTS = frozenset({"streamable_http", "streamable-http", "http", "sse"})


def is_http_transport(conn: dict[str, Any]) -> bool:
    transport = str(conn.get("transport", "")).strip().lower()
    return transport in _HTTP_TRANSPORTS


def normalize_http_connection(conn: dict[str, Any]) -> dict[str, Any]:
    """Validate/normalize an HTTP MCP connection dict for the adapter.

    Accepts ``streamable_http`` / ``streamable-http`` / ``http`` / ``sse``.
    Requires non-empty ``url``.
    """
    if not isinstance(conn, dict):
        raise ValueError("HTTP MCP connection must be an object")
    out = dict(conn)
    transport = str(out.get("transport", "")).strip().lower()
    if transport not in _HTTP_TRANSPORTS:
        raise ValueError(
            f"HTTP MCP transport must be one of {sorted(_HTTP_TRANSPORTS)} "
            f"(got {transport!r})"
        )
    url = str(out.get("url", "")).strip()
    if not url:
        raise ValueError("HTTP MCP connection requires non-empty 'url'")
    # Prefer adapter canonical key for streamable HTTP.
    if transport in {"streamable-http", "http"}:
        out["transport"] = "streamable_http"
    else:
        out["transport"] = transport
    out["url"] = url
    return out


def partition_mcp_connections(
    connections: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Split into (cold_stdio_or_other, sticky_http) maps."""
    cold: dict[str, dict[str, Any]] = {}
    sticky: dict[str, dict[str, Any]] = {}
    for name, conn in connections.items():
        if is_http_transport(conn):
            sticky[name] = normalize_http_connection(conn)
        else:
            cold[name] = dict(conn)
    return cold, sticky


class StickyHttpMcpRuntime:
    """Own sticky MCP sessions on a private event loop/thread."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stack: AsyncExitStack | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._tools: list[BaseTool] = []
        self._closed = False

    @property
    def tools(self) -> list[BaseTool]:
        return list(self._tools)

    def start(
        self,
        connections: dict[str, dict[str, Any]],
        *,
        sync_shim: bool = True,
        timeout_sec: float = 60.0,
    ) -> list[BaseTool]:
        """Open sticky sessions and return tools marshalled onto this loop."""
        if not connections:
            return []
        if self._thread is not None:
            self.close()

        self._ready = threading.Event()
        self._error = None
        self._closed = False
        self._tools = []

        def runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                self._tools = loop.run_until_complete(
                    self._async_open(connections, sync_shim=sync_shim)
                )
                self._ready.set()
                loop.run_forever()
            except BaseException as exc:  # noqa: BLE001
                self._error = exc
                self._ready.set()
            finally:
                try:
                    if self._stack is not None:
                        loop.run_until_complete(self._stack.aclose())
                except Exception:  # noqa: BLE001
                    logger.exception("sticky MCP stack close failed")
                self._stack = None
                loop.close()
                if self._loop is loop:
                    self._loop = None

        self._thread = threading.Thread(
            target=runner, name="mcc-mcp-sticky-http", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=timeout_sec):
            self.close()
            raise TimeoutError(
                f"sticky MCP HTTP session did not start within {timeout_sec}s"
            )
        if self._error is not None:
            err = self._error
            self.close()
            raise RuntimeError(f"sticky MCP HTTP session failed: {err}") from err
        return list(self._tools)

    async def _async_open(
        self,
        connections: dict[str, dict[str, Any]],
        *,
        sync_shim: bool,
    ) -> list[BaseTool]:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools

        stack = AsyncExitStack()
        await stack.__aenter__()
        self._stack = stack
        client = MultiServerMCPClient(connections)
        loaded: list[BaseTool] = []
        for server_name in connections:
            session = await stack.enter_async_context(client.session(server_name))
            raw = await load_mcp_tools(session, server_name=server_name)
            for tool in raw:
                loaded.append(self._bridge_tool(tool, sync_shim=sync_shim))
        return loaded

    def _bridge_tool(self, tool: BaseTool, *, sync_shim: bool) -> BaseTool:
        """Ensure every invoke runs on the sticky loop (session affinity)."""

        def _sync_call(**kwargs: Any) -> Any:
            from mini_claude_code.tools.mcp_loader import _normalize_mcp_result

            if self._loop is None:
                raise RuntimeError("sticky MCP HTTP runtime is not running")
            fut = asyncio.run_coroutine_threadsafe(
                tool.ainvoke(kwargs), self._loop
            )
            return _normalize_mcp_result(fut.result(timeout=120))

        async def _async_call(**kwargs: Any) -> Any:
            from mini_claude_code.tools.mcp_loader import _normalize_mcp_result

            if self._loop is None:
                raise RuntimeError("sticky MCP HTTP runtime is not running")
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is self._loop:
                return _normalize_mcp_result(await tool.ainvoke(kwargs))
            fut = asyncio.run_coroutine_threadsafe(
                tool.ainvoke(kwargs), self._loop
            )
            return await asyncio.get_running_loop().run_in_executor(
                None, lambda: _normalize_mcp_result(fut.result(timeout=120))
            )

        bridged = StructuredTool(
            name=tool.name,
            description=tool.description or tool.name,
            args_schema=getattr(tool, "args_schema", None),
            func=_sync_call if sync_shim else None,
            coroutine=_async_call,
        )
        bridged._mcc_mcp_prepared = True  # type: ignore[attr-defined]
        bridged._mcc_mcp_sync_shim = sync_shim  # type: ignore[attr-defined]
        bridged._mcc_mcp_sticky = True  # type: ignore[attr-defined]
        return bridged

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        self._thread = None
        self._tools = []


_RUNTIME: StickyHttpMcpRuntime | None = None


def get_sticky_http_runtime() -> StickyHttpMcpRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = StickyHttpMcpRuntime()
    return _RUNTIME


def reset_sticky_http_runtime_for_tests() -> None:
    """Close and drop the process singleton (unit/integration teardown)."""
    global _RUNTIME
    if _RUNTIME is not None:
        _RUNTIME.close()
    _RUNTIME = None


def load_sticky_http_tools(
    connections: dict[str, dict[str, Any]],
    *,
    sync_shim: bool = True,
) -> list[BaseTool]:
    """Start (or restart) sticky sessions for HTTP connections; return tools."""
    if not connections:
        return []
    normalized = {
        name: normalize_http_connection(conn) for name, conn in connections.items()
    }
    runtime = get_sticky_http_runtime()
    return runtime.start(normalized, sync_shim=sync_shim)


# Re-export helpers used by tests that patch loaders.
__all__ = [
    "StickyHttpMcpRuntime",
    "get_sticky_http_runtime",
    "is_http_transport",
    "load_sticky_http_tools",
    "normalize_http_connection",
    "partition_mcp_connections",
    "reset_sticky_http_runtime_for_tests",
]
