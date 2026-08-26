"""Tool permissions & Plan Mode (M9) — policy plane, not new graph nodes.

auto / ask / deny are decided *before* the tool body runs. Plan Mode overrides
mutating tools to deny. Ask without LangGraph interrupt uses an optional CLI
callback (M9 simplification); durable pause/resume is M10.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool

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
        # Demo / tests
        "add",
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


def apply_permissions(
    tools: Sequence[BaseTool],
    *,
    plan_mode: bool = False,
    ask_callback: AskCallback | None = None,
) -> list[BaseTool]:
    """Wrap each tool so ToolNode hits the policy plane before the real body."""
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

    def _guarded(**kwargs: Any) -> Any:
        # ToolNode may pass a single dict payload; normalize.
        args = _normalize_args(kwargs)
        mode = resolve_permission(name, plan_mode=plan_mode)
        if mode == "auto":
            return tool.invoke(args)
        if mode == "deny":
            return denial_message(name, mode, plan_mode=plan_mode)
        # ask
        if ask_callback is None:
            return denial_message(
                name,
                mode,
                plan_mode=plan_mode,
                reason="ask required but no interactive approver (non-TTY or tests)",
            )
        approved = bool(ask_callback(name, args if isinstance(args, dict) else {}))
        if not approved:
            return denial_message(
                name,
                mode,
                plan_mode=plan_mode,
                reason="user rejected tool call",
            )
        return tool.invoke(args)

    # Preserve schema for bind_tools; StructuredTool keeps the same contract as ToolNode.
    if args_schema is not None:
        return StructuredTool.from_function(
            func=_guarded,
            name=name,
            description=description,
            args_schema=args_schema,
        )
    return StructuredTool.from_function(
        func=_guarded,
        name=name,
        description=description,
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
    """Blocking y/n ask for TTY CLI. M10 will replace this with interrupt()."""

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
