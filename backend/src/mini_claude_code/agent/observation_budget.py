"""Tool observation budgets (M39).

M7/M37 manage *history* and soft token budgets. A single ToolMessage can still
flood the next ``call_model``. This module is the policy-plane ceiling:

- head+tail truncate with a clear marker
- optional summarize-when-huge (``>= 2×`` budget) — teaching simplification

Per-tool ``MAX_*`` constants remain inner defense; this wrap is the unified gate.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage

TRUNCATION_MARKER = "...[obs-budget truncated {original}→{kept} chars; head+tail]..."

Summarizer = Callable[[str, str], str]  # (tool_name, content) -> summary text


@dataclass(frozen=True)
class ObservationBudgetResult:
    content: str
    truncated: bool
    summarized: bool
    original_chars: int


def estimate_observation_chars(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        # Multimodal-ish blocks — stringify for budget (simplification).
        return len(str(content))
    return len(str(content))


def truncate_head_tail(text: str, max_chars: int, *, head_ratio: float = 0.6) -> str:
    """Keep prefix + suffix when over budget; insert a middle marker."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    ratio = min(0.9, max(0.1, head_ratio))
    # Reserve room for marker inside the budget.
    marker_room = 80
    keep = max(16, max_chars - marker_room)
    head_n = max(8, int(keep * ratio))
    tail_n = max(8, keep - head_n)
    if head_n + tail_n >= len(text):
        return text
    marker = TRUNCATION_MARKER.format(original=len(text), kept=head_n + tail_n)
    return text[:head_n] + "\n\n" + marker + "\n\n" + text[-tail_n:]


def apply_observation_budget(
    content: Any,
    *,
    max_chars: int,
    tool_name: str = "",
    head_ratio: float = 0.6,
    summarize: bool = False,
    summarizer: Summarizer | None = None,
    log: Any = None,
) -> ObservationBudgetResult:
    """Enforce observation budget on one tool result payload."""
    log = log or sys.stderr
    original = estimate_observation_chars(content)
    if max_chars <= 0:
        return ObservationBudgetResult(
            content=content,
            truncated=False,
            summarized=False,
            original_chars=original,
        )

    text = content if isinstance(content, str) else (
        "" if content is None else str(content)
    )
    original = len(text)
    if original <= max_chars:
        return ObservationBudgetResult(
            content=content if isinstance(content, str) else text,
            truncated=False,
            summarized=False,
            original_chars=original,
        )

    summarized = False
    out = text
    if summarize and summarizer is not None and original >= max_chars * 2:
        try:
            summary = summarizer(tool_name or "tool", text)
            if summary and isinstance(summary, str):
                out = (
                    f"[obs-budget summary of {original} chars]\n{summary.strip()}"
                )
                summarized = True
        except Exception as exc:  # noqa: BLE001 — fall back to truncate
            print(
                f"[obs-budget] summarize failed ({exc}); truncating instead",
                file=log,
            )
            out = text

    truncated = False
    if len(out) > max_chars:
        out = truncate_head_tail(out, max_chars, head_ratio=head_ratio)
        truncated = True
    elif not summarized and original > max_chars:
        truncated = True

    if truncated or summarized:
        print(
            f"[obs-budget] tool={tool_name or '?'} "
            f"{original}→{len(out)} chars "
            f"(truncated={truncated} summarized={summarized})",
            file=log,
        )

    return ObservationBudgetResult(
        content=out,
        truncated=truncated,
        summarized=summarized,
        original_chars=original,
    )


def apply_budget_to_tool_message(
    message: ToolMessage,
    *,
    max_chars: int,
    head_ratio: float = 0.6,
    summarize: bool = False,
    summarizer: Summarizer | None = None,
    log: Any = None,
) -> ToolMessage:
    result = apply_observation_budget(
        message.content,
        max_chars=max_chars,
        tool_name=str(message.name or ""),
        head_ratio=head_ratio,
        summarize=summarize,
        summarizer=summarizer,
        log=log,
    )
    if not result.truncated and not result.summarized:
        return message
    # Prefer copy to preserve extra fields across LangChain versions.
    try:
        return message.model_copy(update={"content": result.content})
    except Exception:  # noqa: BLE001
        return ToolMessage(
            content=result.content,
            tool_call_id=message.tool_call_id,
            name=message.name,
        )


def apply_budget_to_tool_outputs(
    outputs: Any,
    *,
    max_chars: int,
    head_ratio: float = 0.6,
    summarize: bool = False,
    summarizer: Summarizer | None = None,
    log: Any = None,
    messages_key: str = "messages",
) -> Any:
    """Post-process ToolNode combine result (list or ``{messages: [...]}``)."""
    if max_chars <= 0:
        return outputs

    def _map_msg(m: Any) -> Any:
        if isinstance(m, ToolMessage):
            return apply_budget_to_tool_message(
                m,
                max_chars=max_chars,
                head_ratio=head_ratio,
                summarize=summarize,
                summarizer=summarizer,
                log=log,
            )
        return m

    if isinstance(outputs, list):
        return [_map_msg(m) for m in outputs]
    if isinstance(outputs, dict) and messages_key in outputs:
        msgs = outputs[messages_key]
        if isinstance(msgs, Sequence):
            return {
                **outputs,
                messages_key: [_map_msg(m) for m in msgs],
            }
    return outputs


def default_observation_summarizer(llm: Any) -> Summarizer:
    """Build a no-tools summarizer for huge tool dumps (optional M39 path)."""

    def _summarize(tool_name: str, content: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        from mini_claude_code.agent.retry import invoke_with_retry
        from mini_claude_code.config import get_settings

        # Cap what we send to the summarizer itself.
        sample = content if len(content) <= 24_000 else (
            content[:12_000] + "\n…\n" + content[-12_000:]
        )
        prompt = (
            f"Summarize this `{tool_name}` tool observation for a coding agent. "
            "Keep errors, paths, exit codes, and key findings. Be concise.\n\n"
            f"{sample}"
        )

        def _call() -> Any:
            return llm.invoke(
                [
                    SystemMessage(content="You compress tool outputs. No tools."),
                    HumanMessage(content=prompt),
                ]
            )

        response = invoke_with_retry(_call, settings=get_settings())
        raw = getattr(response, "content", response)
        return raw if isinstance(raw, str) else str(raw)

    return _summarize
