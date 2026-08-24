"""Render LangGraph stream events for the agent CLI (M6).

Not a second entrypoint — `cli.py` is the only CLI. This module only turns
`graph.stream(...)` chunks into stdout (tokens + tool/node milestones).

`messages` = LLM tokens (only if call_model passes config into the model).
`updates` = per-node milestones (tool lifecycle is visible here).
"""

from __future__ import annotations

import sys
from typing import Any, Iterator, TextIO

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage


def iter_agent_stream(
    graph: Any,
    prompt: str,
    config: dict,
) -> Iterator[tuple[str, Any]]:
    """Yield `(mode, data)` from messages+updates (+values for final state)."""
    yield from graph.stream(
        {"messages": [HumanMessage(content=prompt)]},
        config=config,
        stream_mode=["messages", "updates", "values"],
    )


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # Some providers return list-of-blocks; flatten text parts best-effort.
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def consume_agent_stream(
    graph: Any,
    prompt: str,
    config: dict,
    *,
    out: TextIO | None = None,
) -> list[Any]:
    """Print live tokens/tool events; return final messages list (may be empty)."""
    out = out or sys.stdout
    final_messages: list[Any] = []
    printed_ai = False

    for item in iter_agent_stream(graph, prompt, config):
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        mode, data = item

        if mode == "values" and isinstance(data, dict):
            final_messages = list(data.get("messages") or [])
            continue

        if mode == "messages":
            msg, _meta = data
            if isinstance(msg, (AIMessage, AIMessageChunk)):
                text = _content_text(msg.content)
                if text:
                    if not printed_ai:
                        out.write("AI: ")
                        printed_ai = True
                    out.write(text)
                    out.flush()
            continue

        if mode == "updates" and isinstance(data, dict):
            if printed_ai:
                out.write("\n")
                printed_ai = False
            if "tools" in data:
                payload = data["tools"]
                msgs = []
                if isinstance(payload, dict):
                    msgs = payload.get("messages") or []
                for tm in msgs:
                    if isinstance(tm, ToolMessage):
                        preview = _content_text(tm.content)
                        if len(preview) > 240:
                            preview = preview[:240] + "…"
                        out.write(f"[tool:{tm.name}] {preview}\n")
                        out.flush()
            if "call_model" in data:
                payload = data["call_model"]
                msgs = []
                if isinstance(payload, dict):
                    msgs = payload.get("messages") or []
                for am in msgs:
                    if isinstance(am, AIMessage) and am.tool_calls:
                        calls = ", ".join(
                            f"{tc.get('name')}({tc.get('args')})"
                            for tc in am.tool_calls
                        )
                        out.write(f"[model→tools] {calls}\n")
                        out.flush()
            continue

    if printed_ai:
        out.write("\n")
        out.flush()
    out.write("=== done ===\n")
    out.flush()
    return final_messages
