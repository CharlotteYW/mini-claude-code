"""Human-in-the-loop helpers around LangGraph interrupt / Command (M10).

Policy (auto/ask/deny) lives in permissions.py. This module only: detect
pending interrupts, prompt a human, and resume with Command(resume=bool).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, TextIO

from langchain_core.messages import HumanMessage
from langgraph.types import Command


def pending_interrupt_values(graph: Any, config: dict) -> list[Any]:
    """Return interrupt payloads for the current thread (empty if none)."""
    snap = graph.get_state(config)
    interrupts = getattr(snap, "interrupts", None) or ()
    return [getattr(item, "value", item) for item in interrupts]


def result_interrupt_values(result: Any) -> list[Any]:
    """Pull payloads from an invoke result's ``__interrupt__`` key if present."""
    if not isinstance(result, dict):
        return []
    raw = result.get("__interrupt__") or ()
    return [getattr(item, "value", item) for item in raw]


def format_approval_prompt(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("type") == "tool_approval":
        tool = payload.get("tool", "?")
        args = payload.get("args") or {}
        preview = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:8])
        if len(args) > 8:
            preview += ", …"
        return f"[hitl] Allow `{tool}` ({preview})? [y/N]"
    return f"[hitl] Resume with approval? payload={payload!r} [y/N]"


def prompt_approval(
    payload: Any,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> bool:
    """TTY y/n for one interrupt payload. Returns True to approve."""

    def _in(prompt: str) -> str:
        if input_fn is not None:
            return input_fn(prompt)
        return input(prompt)

    def _out(text: str) -> None:
        if output_fn is not None:
            output_fn(text)
            return
        print(text, flush=True)

    _out(format_approval_prompt(payload))
    try:
        answer = _in("allow> ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def invoke_with_hitl(
    graph: Any,
    prompt: str,
    config: dict,
    *,
    approve_fn: Callable[[Any], bool] | None = None,
) -> tuple[dict[str, Any] | None, int]:
    """Invoke until completion, prompting on each ask ``interrupt``.

    Returns ``(final_result_or_none, exit_code)``.
    **Simplification:** uses ``invoke`` (not token streaming) so Command resume
    stays obvious; Plan Mode can still stream separately in the CLI.
    """
    decide = approve_fn or prompt_approval
    payload: Any = {"messages": [HumanMessage(content=prompt)]}

    while True:
        try:
            result = graph.invoke(payload, config=config)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: agent run failed: {exc}", file=sys.stderr)
            return None, 1

        pending = result_interrupt_values(result) or pending_interrupt_values(
            graph, config
        )
        if not pending:
            return result if isinstance(result, dict) else None, 0

        # Single bool resume covers the usual one-tool interrupt; if the human
        # rejects any pending payload, resume False for the batch.
        approved = True
        for item in pending:
            if not decide(item):
                approved = False
                break
        payload = Command(resume=approved)
