"""Content-aware tool policy (M26).

M9 gates *tool names*; M15 hooks see *name/args*. This module inspects
*returned text* (title / first line / markdown H1) for markers like ``no-ai``
or ``CONFIDENTIAL`` and replaces the body with a deny string so the model
never sees the secret.

**Client wrap** cannot trust a hostile MCP server that strips markers — teach
**server-enforced** policy in ``mcp_servers/fake_docs.py`` as well.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.config import Settings, get_settings

DEFAULT_MARKERS: tuple[str, ...] = ("no-ai", "confidential")

# Tools whose string results are screened (MCP read_doc + builtin read_file).
DEFAULT_WRAP_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "read_file",
        "read_doc",
        "read_document",
    }
)

_DENY_PREFIX = "CONTENT_POLICY_DENIED:"


def parse_markers(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    """Parse comma-separated markers; empty → defaults."""
    if raw is None:
        return DEFAULT_MARKERS
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return tuple(parts) if parts else DEFAULT_MARKERS
    parts = [str(p).strip() for p in raw if str(p).strip()]
    return tuple(parts) if parts else DEFAULT_MARKERS


def first_nonempty_line(text: str) -> str:
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def markdown_h1_title(text: str) -> str | None:
    """First markdown AT1 if it appears before other non-empty content."""
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip() or None
        return None
    return None


def find_policy_marker(
    text: str,
    *,
    title: str | None = None,
    markers: Sequence[str] | None = None,
) -> str | None:
    """Return the matched marker (original casing from config) or None."""
    markers = parse_markers(markers)
    haystacks: list[str] = []
    if title and title.strip():
        haystacks.append(title.strip())
    fl = first_nonempty_line(text)
    if fl:
        haystacks.append(fl)
    h1 = markdown_h1_title(text)
    if h1:
        haystacks.append(h1)

    for hay in haystacks:
        lower = hay.lower()
        for marker in markers:
            if marker.lower() in lower:
                return marker
    return None


def content_policy_denial(marker: str, *, source: str = "content") -> str:
    return (
        f"{_DENY_PREFIX} marker={marker!r} source={source} — "
        "document body withheld from the model (M26 content policy). "
        "Do not invent or guess the withheld contents."
    )


def is_already_denied(result: Any) -> bool:
    return isinstance(result, str) and result.startswith(_DENY_PREFIX)


def filter_tool_result(
    result: Any,
    *,
    title: str | None = None,
    markers: Sequence[str] | None = None,
    source: str = "client_wrap",
) -> Any:
    """If result is text that violates policy, replace with denial string."""
    if is_already_denied(result):
        return result
    if not isinstance(result, str):
        return result
    # Don't treat tool ERROR strings as docs.
    if result.startswith(("ERROR:", "PERMISSION_DENIED:")):
        return result
    matched = find_policy_marker(result, title=title, markers=markers)
    if matched is None:
        return result
    return content_policy_denial(matched, source=source)


def should_wrap_tool(name: str, *, extra_names: Sequence[str] | None = None) -> bool:
    names = set(DEFAULT_WRAP_TOOL_NAMES)
    if extra_names:
        names.update(extra_names)
    if name in names:
        return True
    return bool(re.match(r"^read[_-]", name, flags=re.IGNORECASE))


def apply_content_policy_wrap(
    tools: Sequence[BaseTool],
    *,
    settings: Settings | None = None,
    markers: Sequence[str] | None = None,
    tool_names: Sequence[str] | None = None,
) -> list[BaseTool]:
    """Wrap matching tools so returned bodies are screened (func + coroutine)."""
    settings = settings or get_settings()
    if not settings.content_policy_enabled:
        return list(tools)
    marker_list = parse_markers(
        markers if markers is not None else settings.content_policy_markers
    )

    out: list[BaseTool] = []
    for tool in tools:
        if not should_wrap_tool(tool.name, extra_names=tool_names):
            out.append(tool)
            continue
        out.append(_wrap_one(tool, markers=marker_list))
    return out


def _wrap_one(tool: BaseTool, *, markers: Sequence[str]) -> BaseTool:
    name = tool.name
    description = tool.description or name
    args_schema = getattr(tool, "args_schema", None)

    def _title_from_args(args: Any) -> str | None:
        if isinstance(args, dict):
            for key in ("title", "name", "doc_id", "path"):
                val = args.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    def _guarded(**kwargs: Any) -> Any:
        args = _normalize_args(kwargs)
        result = tool.invoke(args)
        return filter_tool_result(
            result,
            title=_title_from_args(args),
            markers=markers,
            source=f"client_wrap:{name}",
        )

    async def _aguard(**kwargs: Any) -> Any:
        args = _normalize_args(kwargs)
        result = await tool.ainvoke(args)
        return filter_tool_result(
            result,
            title=_title_from_args(args),
            markers=markers,
            source=f"client_wrap:{name}",
        )

    wrapped = StructuredTool(
        name=name,
        description=description,
        args_schema=args_schema,
        func=_guarded,
        coroutine=_aguard,
    )
    wrapped._mcc_content_policy = True  # type: ignore[attr-defined]
    return wrapped


def _normalize_args(kwargs: dict[str, Any]) -> Any:
    if len(kwargs) == 1 and "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
        return kwargs["kwargs"]
    return dict(kwargs)
