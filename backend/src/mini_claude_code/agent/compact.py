"""Context compaction (M7): summarize older messages when the prompt gets large.

Simplification: approximate tokens as len(chars)/4; rewrite live `messages`
in graph state (production often keeps a full audit transcript + a separate
model view).
"""

from __future__ import annotations

import sys
from typing import Any, Callable, Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

Summarizer = Callable[[Sequence[BaseMessage]], BaseMessage]

_SUMMARY_SYSTEM = (
    "You summarize prior conversation for a coding agent. "
    "Keep: user goals, file paths, decisions, errors, and important tool outcomes. "
    "Omit chatter and huge dumps. Be concise (short paragraphs or bullets)."
)


def estimate_tokens(messages: Sequence[BaseMessage]) -> int:
    """Rough token estimate — not tiktoken. Teaching shortcut."""
    total_chars = 0
    for message in messages:
        total_chars += len(_message_text(message))
        if isinstance(message, AIMessage) and message.tool_calls:
            total_chars += len(str(message.tool_calls))
    return max(1, total_chars // 4) if total_chars else 0


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def format_messages_for_summary(messages: Sequence[BaseMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        role = type(message).__name__.replace("Message", "").upper()
        body = _message_text(message)
        if isinstance(message, AIMessage) and message.tool_calls:
            calls = ", ".join(
                f"{tc.get('name')}({tc.get('args')})" for tc in message.tool_calls
            )
            body = (body + f"\n[tool_calls: {calls}]").strip()
        if isinstance(message, ToolMessage):
            preview = body if len(body) <= 500 else body[:500] + "…"
            lines.append(f"TOOL[{message.name}]: {preview}")
        else:
            lines.append(f"{role}: {body}")
    return "\n\n".join(lines)


def safe_prefix_end(messages: Sequence[BaseMessage], keep_recent: int) -> int:
    """Index where the compactable prefix ends (exclusive).

    Guarantees the recent window does not start mid tool-call group and the
    prefix does not keep an AIMessage(tool_calls) whose ToolMessages are recent.
    """
    if keep_recent <= 0 or len(messages) <= keep_recent:
        return 0

    cut = len(messages) - keep_recent
    # Recent must not start on orphan ToolMessage(s).
    while cut > 0 and isinstance(messages[cut], ToolMessage):
        cut -= 1

    # If an AI tool-call sits just before cut but its results are in recent,
    # pull that AI into recent as well.
    while cut > 0:
        prev = messages[cut - 1]
        if not (isinstance(prev, AIMessage) and prev.tool_calls):
            break
        ids = {
            tc.get("id")
            for tc in prev.tool_calls
            if isinstance(tc, dict) and tc.get("id")
        }
        if not ids:
            break
        if any(
            isinstance(m, ToolMessage) and m.tool_call_id in ids
            for m in messages[cut:]
        ):
            cut -= 1
            continue
        break

    return max(0, cut)


def default_summarizer(llm: Any) -> Summarizer:
    """Build a no-tools summarizer using the same chat model family."""

    def _summarize(prefix: Sequence[BaseMessage]) -> BaseMessage:
        transcript = format_messages_for_summary(prefix)
        response = llm.invoke(
            [
                SystemMessage(content=_SUMMARY_SYSTEM),
                HumanMessage(content=transcript),
            ]
        )
        text = _message_text(response) if isinstance(response, BaseMessage) else str(response)
        return SystemMessage(content=f"[conversation summary]\n{text.strip()}")

    return _summarize


def maybe_compact_messages(
    messages: Sequence[BaseMessage],
    *,
    threshold_tokens: int,
    keep_recent: int,
    summarizer: Summarizer,
    log: Any = None,
) -> tuple[list[BaseMessage], bool]:
    """Return (messages, did_compact).

    If under threshold, or nothing safe to summarize, returns the original list.
    """
    log = log or sys.stderr
    original = list(messages)
    if threshold_tokens <= 0:
        return original, False

    size = estimate_tokens(original)
    if size <= threshold_tokens:
        return original, False

    cut = safe_prefix_end(original, keep_recent)
    if cut <= 0:
        return original, False

    prefix = original[:cut]
    recent = original[cut:]
    # Need a meaningful prefix (more than noise).
    if estimate_tokens(prefix) < max(32, threshold_tokens // 10):
        return original, False

    summary = summarizer(prefix)
    compacted: list[BaseMessage] = [summary, *recent]
    print(
        f"[compact] estimated_tokens {size}→{estimate_tokens(compacted)} "
        f"(messages {len(original)}→{len(compacted)})",
        file=log,
    )
    return compacted, True
