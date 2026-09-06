"""Tool permissions & Plan Mode (M9) + HITL interrupt on ask (M10).

auto / ask / deny are decided *before* the tool body runs. Plan Mode overrides
mutating tools to deny. Ask uses LangGraph ``interrupt()`` so the graph pauses
with a checkpointer; resume via ``Command(resume=bool)``. Optional
``ask_callback`` remains only for unit tests that bypass interrupt.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt

PermissionMode = Literal["auto", "ask", "deny"]

# Actual default tool names in this repo (FS uses glob_files / grep_files).
READ_SAFE_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "glob_files",
        "grep_files",
        "git_status",
        "git_diff",
        "git_log",
        "recall_facts",
        "recall_notes",
        "search_chunks",
        "search_keyword",
        # Demo / tests (M1) + M14 in-repo MCP echo_math demos
        "add",
        "echo",
        # M26 fake docs MCP
        "list_docs",
        "read_doc",
        # M12: delegation is orchestration; child tools are still permissioned.
        "run_subagent",
        # M13: loading playbook text into context.
        "load_skill",
        # M19: local format + tests (read-only side effects on CI logs only).
        "ship_check",
    }
)

MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "run_shell",
        "git_commit",
        "remember_fact",
        "remember_note",
        "ingest_docs",
        "open_pull_request",
        "git_push",
    }
)

AskCallback = Callable[[str, dict[str, Any]], bool]


def default_mode_for(tool_name: str) -> PermissionMode:
    """Baseline policy when not in Plan Mode. Unknown tools → ask (cautious)."""
    if tool_name in READ_SAFE_TOOLS:
        return "auto"
    if tool_name in MUTATING_TOOLS:
        return "ask"
    return "ask"


def resolve_permission(tool_name: str, *, plan_mode: bool = False) -> PermissionMode:
    """Effective mode for one tool under current Plan Mode."""
    base = default_mode_for(tool_name)
    if plan_mode and tool_name in MUTATING_TOOLS:
        return "deny"
    if plan_mode and tool_name not in READ_SAFE_TOOLS and tool_name not in MUTATING_TOOLS:
        # Unknown tools stay ask→ but Plan Mode should not silently auto them.
        return "deny"
    return base


def denial_message(
    tool_name: str,
    mode: PermissionMode,
    *,
    plan_mode: bool,
    reason: str | None = None,
) -> str:
    """Clear ToolMessage content so the model can recover without side effects."""
    if reason:
        detail = reason
    elif plan_mode and mode == "deny":
        detail = "blocked by Plan Mode (read-only session)"
    elif mode == "deny":
        detail = "denied by tool permission policy"
    else:
        detail = "ask rejected or non-interactive (no approval)"
    return (
        f"PERMISSION_DENIED: tool={tool_name} mode={mode} "
        f"plan_mode={plan_mode}: {detail}. "
        "Do not retry the same mutating call unless the user changes mode/policy."
    )


def approval_interrupt_payload(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Payload shown to the human when ask pauses the graph (M10)."""
    return {
        "type": "tool_approval",
        "tool": tool_name,
        "args": args,
    }


def apply_permissions(
    tools: Sequence[BaseTool],
    *,
    plan_mode: bool = False,
    ask_callback: AskCallback | None = None,
) -> list[BaseTool]:
    """Wrap each tool so ToolNode hits the policy plane before the real body.

    On ``ask``: call ``interrupt(payload)`` unless ``ask_callback`` is set
    (test-only bypass that skips durable HITL).
    """
    return [
        _wrap_one(t, plan_mode=plan_mode, ask_callback=ask_callback) for t in tools
    ]


def _wrap_one(
    tool: BaseTool,
    *,
    plan_mode: bool,
    ask_callback: AskCallback | None,
) -> BaseTool:
    name = tool.name
    description = tool.description or name
    args_schema = getattr(tool, "args_schema", None)

    def _decide(args_dict: dict[str, Any]) -> tuple[PermissionMode, Any | None]:
        """Return (mode, denial_string_or_None). None denial means proceed."""
        mode = resolve_permission(name, plan_mode=plan_mode)
        if mode == "auto":
            return mode, None
        if mode == "deny":
            return mode, denial_message(name, mode, plan_mode=plan_mode)
        if ask_callback is not None:
            approved = bool(ask_callback(name, args_dict))
        else:
            approved = bool(
                interrupt(approval_interrupt_payload(name, args_dict))
            )
        if not approved:
            return mode, denial_message(
                name,
                mode,
                plan_mode=plan_mode,
                reason="user rejected tool call",
            )
        return mode, None

    def _guarded(**kwargs: Any) -> Any:
        args = _normalize_args(kwargs)
        args_dict = args if isinstance(args, dict) else {}
        _mode, denied = _decide(args_dict)
        if denied is not None:
            return denied
        return tool.invoke(args)

    async def _aguard(**kwargs: Any) -> Any:
        # M22: async ToolNode uses ainvoke — must not fall back to sync invoke
        # (which would asyncio.run MCP tools inside a running loop).
        args = _normalize_args(kwargs)
        args_dict = args if isinstance(args, dict) else {}
        _mode, denied = _decide(args_dict)
        if denied is not None:
            return denied
        return await tool.ainvoke(args)

    return StructuredTool(
        name=name,
        description=description,
        args_schema=args_schema,
        func=_guarded,
        coroutine=_aguard,
    )


def _normalize_args(kwargs: Mapping[str, Any] | dict[str, Any]) -> Any:
    """StructuredTool.from_function(**kwargs) vs single-dict invoke."""
    if len(kwargs) == 1 and "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
        return kwargs["kwargs"]
    return dict(kwargs)


def make_cli_ask_callback(
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> AskCallback:
    """Deprecated for production CLI — prefer interrupt + Command (M10).

    Kept for unit tests that need a synchronous approve without a checkpointer.
    """

    def _input(prompt: str) -> str:
        if input_fn is not None:
            return input_fn(prompt)
        return input(prompt)

    def _output(text: str) -> None:
        if output_fn is not None:
            output_fn(text)
            return
        print(text, flush=True)

    def ask(tool_name: str, args: dict[str, Any]) -> bool:
        preview = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:8])
        if len(args) > 8:
            preview += ", …"
        _output(f"\n[permissions] Allow `{tool_name}` ({preview})? [y/N]")
        try:
            answer = _input("allow> ").strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes"}

    return ask
