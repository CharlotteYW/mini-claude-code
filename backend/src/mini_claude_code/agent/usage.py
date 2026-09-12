"""Per-run LLM token usage accounting (M17 / M37).

Reads ``AIMessage.usage_metadata`` when the provider returns it; otherwise falls
back to ``estimate_tokens`` (same chars/4 shortcut as M7 compaction).

M37: also records cache_read / cache_creation from ``input_token_details`` (or
legacy top-level aliases) and optional pre-call prompt/budget estimates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig

from mini_claude_code.agent.compact import estimate_tokens

USAGE_ACCUMULATOR_KEY = "usage_accumulator"


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def extract_cache_tokens(meta: dict[str, Any] | None) -> tuple[int, int]:
    """Return (cache_read, cache_creation) from LangChain usage_metadata."""
    if not meta:
        return 0, 0
    details = meta.get("input_token_details")
    read = create = 0
    if isinstance(details, dict):
        read = _int_or_zero(details.get("cache_read"))
        create = _int_or_zero(details.get("cache_creation"))
    # Legacy / raw Anthropic-style aliases if details omitted.
    if read == 0:
        read = _int_or_zero(
            meta.get("cache_read") or meta.get("cache_read_input_tokens")
        )
    if create == 0:
        create = _int_or_zero(
            meta.get("cache_creation") or meta.get("cache_creation_input_tokens")
        )
    return read, create


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
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    # Last pre-call snapshot (M37 budget awareness).
    last_prompt_estimate: int | None = None
    soft_budget: int | None = None
    effective_compact_at: int | None = None

    def note_prompt_stats(
        self,
        *,
        prompt_estimate: int,
        soft_budget: int,
        effective_compact_at: int,
    ) -> None:
        self.last_prompt_estimate = int(prompt_estimate)
        self.soft_budget = int(soft_budget)
        self.effective_compact_at = int(effective_compact_at)

    def record(self, message: BaseMessage) -> None:
        if not isinstance(message, AIMessage):
            return
        self.llm_calls += 1
        meta = message.usage_metadata
        if meta and any(
            meta.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
        ):
            self.calls_with_metadata += 1
            self.input_tokens += _int_or_zero(meta.get("input_tokens"))
            self.output_tokens += _int_or_zero(meta.get("output_tokens"))
            reported_total = meta.get("total_tokens")
            if reported_total is not None:
                self.total_tokens += _int_or_zero(reported_total)
            else:
                self.total_tokens += _int_or_zero(meta.get("input_tokens")) + _int_or_zero(
                    meta.get("output_tokens")
                )
            read, create = extract_cache_tokens(dict(meta) if meta else None)
            self.cache_read_tokens += read
            self.cache_creation_tokens += create
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
        if self.cache_read_tokens or self.cache_creation_tokens:
            lines.append(f"  cache_read_tokens:      {self.cache_read_tokens}")
            lines.append(f"  cache_creation_tokens:  {self.cache_creation_tokens}")
        else:
            lines.append("  cache:                  n/a")
        if self.last_prompt_estimate is not None:
            lines.append(f"  prompt_estimate:        {self.last_prompt_estimate}")
            budget = self.soft_budget if self.soft_budget and self.soft_budget > 0 else None
            lines.append(
                f"  soft_budget:            {budget if budget is not None else 'n/a'}"
            )
            eff = self.effective_compact_at
            lines.append(
                f"  effective_compact_at:    {eff if eff and eff > 0 else 'disabled'}"
            )
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
