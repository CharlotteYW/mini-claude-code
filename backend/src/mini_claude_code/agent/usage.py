"""Per-run LLM token usage accounting (M17).

Reads ``AIMessage.usage_metadata`` when the provider returns it; otherwise falls
back to ``estimate_tokens`` (same chars/4 shortcut as M7 compaction).
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig

from mini_claude_code.agent.compact import estimate_tokens

USAGE_ACCUMULATOR_KEY = "usage_accumulator"


@dataclass
class UsageAccumulator:
    """In-memory totals for one agent run (not billing-grade)."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    estimated_fallback_tokens: int = 0
    calls_with_metadata: int = 0
    calls_without_metadata: int = 0

    def record(self, message: BaseMessage) -> None:
        if not isinstance(message, AIMessage):
            return
        self.llm_calls += 1
        meta = message.usage_metadata
        if meta and any(
            meta.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
        ):
            self.calls_with_metadata += 1
            self.input_tokens += int(meta.get("input_tokens") or 0)
            self.output_tokens += int(meta.get("output_tokens") or 0)
            reported_total = meta.get("total_tokens")
            if reported_total is not None:
                self.total_tokens += int(reported_total)
            else:
                self.total_tokens += int(meta.get("input_tokens") or 0) + int(
                    meta.get("output_tokens") or 0
                )
            return
        self.calls_without_metadata += 1
        est = estimate_tokens([message])
        self.estimated_fallback_tokens += est
        self.total_tokens += est

    def format_footer(self) -> str:
        lines = [
            "=== usage ===",
            f"  llm_calls:              {self.llm_calls}",
            f"  input_tokens:           {self.input_tokens}",
            f"  output_tokens:          {self.output_tokens}",
            f"  total_tokens:           {self.total_tokens}",
        ]
        if self.calls_without_metadata:
            lines.append(
                f"  estimated_fallback:     {self.estimated_fallback_tokens} "
                f"({self.calls_without_metadata} call(s) without usage_metadata)"
            )
        lines.append("=== end usage ===")
        return "\n".join(lines)


def get_usage_accumulator(
    config: RunnableConfig | dict | None,
) -> UsageAccumulator | None:
    if not config:
        return None
    conf = config.get("configurable") or {}
    acc = conf.get(USAGE_ACCUMULATOR_KEY)
    return acc if isinstance(acc, UsageAccumulator) else None


def record_llm_usage(
    response: BaseMessage,
    config: RunnableConfig | dict | None,
    *,
    fallback: UsageAccumulator | None = None,
) -> None:
    acc = get_usage_accumulator(config) or fallback
    if acc is not None:
        acc.record(response)
