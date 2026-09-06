"""Lifecycle hooks (M15/M24): PreToolUse / PostToolUse / Stop.

Call order for tools (compose with M9):
  Pre hooks → permissions / HITL → tool body → Post hooks

Stop runs when ``call_model`` produces an AIMessage with no tool_calls
(best-effort “this turn is done,” not process exit).

Handlers: in-process Python ids (M15) and optional shell/script runners (M24).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.config import Settings, get_settings, resolve_workspace_root

logger = logging.getLogger(__name__)

HookEvent = Literal["pre_tool_use", "post_tool_use", "stop"]


@dataclass
class PreResult:
    """Decision from a PreToolUse handler."""

    allow: bool = True
    reason: str | None = None
    args: dict[str, Any] | None = None  # optional arg rewrite


@dataclass
class HookContext:
    event: HookEvent
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    stop_content: str | None = None


PreHandler = Callable[[HookContext], PreResult | dict[str, Any] | bool | str | None]
PostHandler = Callable[[HookContext], str | None]
StopHandler = Callable[[HookContext], None]


@dataclass
class HookRegistry:
    pre: list[PreHandler] = field(default_factory=list)
    post: list[PostHandler] = field(default_factory=list)
    stop: list[StopHandler] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.pre or self.post or self.stop)


def hook_denied_message(tool_name: str, reason: str | None = None) -> str:
    detail = reason or "blocked by PreToolUse hook"
    return (
        f"HOOK_DENIED: tool={tool_name}: {detail}. "
        "Do not retry the same call unless hooks/config change."
    )


def _resolve_handler(
    handler_id: str, table: Mapping[str, Callable[..., Any]]
) -> Callable[..., Any]:
    if handler_id not in table:
        known = ", ".join(sorted(table)) or "(none)"
        raise ValueError(f"Unknown hook handler id {handler_id!r}; known: {known}")
    return table[handler_id]


def _entry_kind(item: Any) -> str:
    if isinstance(item, str):
        return "id"
    if isinstance(item, dict):
        if "type" in item:
            return str(item.get("type") or "").strip().lower() or "unknown"
        if "id" in item:
            return "id"
    return "invalid"


def load_hook_registry_from_dict(
    data: Mapping[str, Any] | None,
    *,
    settings: Settings | None = None,
    workspace_root: Path | None = None,
    base_dir: Path | None = None,
) -> HookRegistry:
    """Build registry from parsed YAML/JSON object (ids + optional shell/script)."""
    from mini_claude_code.agent import hook_demos
    from mini_claude_code.agent.shell_hooks import (
        is_path_allowed,
        make_shell_post_handler,
        make_shell_pre_handler,
        resolve_script_argv,
    )

    settings = settings or get_settings()
    root = workspace_root or resolve_workspace_root(settings)

    if not data:
        return HookRegistry()

    pre_items = list(data.get("pre_tool_use") or [])
    post_items = list(data.get("post_tool_use") or [])
    stop_items = list(data.get("stop") or [])

    pre: list[PreHandler] = []
    post: list[PostHandler] = []
    stop: list[StopHandler] = []

    def _shell_or_skip(entry: dict[str, Any], *, phase: str) -> None:
        if not settings.hook_shell_enabled:
            logger.warning(
                "Skipping shell/script hook (HOOK_SHELL_ENABLED=0): %r", entry
            )
            return
        try:
            argv = resolve_script_argv(entry, base_dir=base_dir)
        except ValueError as exc:
            raise ValueError(f"Invalid {phase} shell hook: {exc}") from exc

        typ = str(entry.get("type") or "").lower()
        if typ == "script":
            check_path = Path(str(entry["path"])).resolve()
        else:
            # shell command: trust via base_dir under plugins/ or allowlist "*"
            if base_dir is not None and is_path_allowed(
                base_dir, settings=settings, workspace_root=root
            ):
                check_path = base_dir.resolve()
            elif any(
                p.strip() == "*" for p in settings.hook_shell_allowlist.split(",")
            ):
                check_path = Path(argv[0]).resolve()
            else:
                raise ValueError(
                    "shell hook requires plugin base_dir under workspace/plugins/ "
                    "or HOOK_SHELL_ALLOWLIST including '*'"
                )

        if not is_path_allowed(check_path, settings=settings, workspace_root=root):
            raise ValueError(
                f"shell/script hook path not allowlisted: {check_path} "
                f"(set HOOK_SHELL_ALLOWLIST or place under workspace/plugins/)"
            )
        label = str(entry.get("path") or entry.get("command") or argv[0])
        if phase == "pre":
            pre.append(
                make_shell_pre_handler(
                    argv, settings=settings, label=label, cwd=base_dir
                )
            )
        elif phase == "post":
            post.append(
                make_shell_post_handler(
                    argv, settings=settings, label=label, cwd=base_dir
                )
            )
        else:
            raise ValueError("shell/script hooks not supported for stop in M24")

    for item in pre_items:
        kind = _entry_kind(item)
        if kind == "id":
            hid = item if isinstance(item, str) else str(item["id"])
            pre.append(_resolve_handler(hid, hook_demos.DEMO_PRE_HANDLERS))
        elif kind in ("script", "shell"):
            assert isinstance(item, dict)
            _shell_or_skip(item, phase="pre")
        else:
            raise ValueError(f"Invalid pre_tool_use hook entry: {item!r}")

    for item in post_items:
        kind = _entry_kind(item)
        if kind == "id":
            hid = item if isinstance(item, str) else str(item["id"])
            post.append(_resolve_handler(hid, hook_demos.DEMO_POST_HANDLERS))
        elif kind in ("script", "shell"):
            assert isinstance(item, dict)
            _shell_or_skip(item, phase="post")
        else:
            raise ValueError(f"Invalid post_tool_use hook entry: {item!r}")

    for item in stop_items:
        kind = _entry_kind(item)
        if kind == "id":
            hid = item if isinstance(item, str) else str(item["id"])
            stop.append(_resolve_handler(hid, hook_demos.DEMO_STOP_HANDLERS))
        elif kind in ("script", "shell"):
            raise ValueError("shell/script stop hooks not supported in M24")
        else:
            raise ValueError(f"Invalid stop hook entry: {item!r}")

    return HookRegistry(pre=pre, post=post, stop=stop)


def load_hook_registry_from_yaml(
    path: Path,
    *,
    settings: Settings | None = None,
    workspace_root: Path | None = None,
) -> HookRegistry:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Hooks file must be a mapping: {path}")
    return load_hook_registry_from_dict(
        data,
        settings=settings,
        workspace_root=workspace_root,
        base_dir=path.parent.resolve(),
    )


def demo_hook_registry() -> HookRegistry:
    """Built-in teaching set (same as hooks.example.yaml)."""
    return load_hook_registry_from_dict(
        {
            "pre_tool_use": ["block_dangerous_shell"],
            "post_tool_use": ["redact_secret_pattern", "append_audit_marker"],
            "stop": ["log_stop"],
        }
    )


def resolve_hook_registry(
    settings: Settings | None = None,
    *,
    workspace_root: Path | None = None,
) -> HookRegistry:
    """Resolve hooks: base config + merged plugin hook sections (M16/M24)."""
    from mini_claude_code.agent.plugins import resolve_merged_hooks_dict

    settings = settings or get_settings()
    root = workspace_root or resolve_workspace_root(settings)
    merged = resolve_merged_hooks_dict(settings, workspace_root=root)
    if merged is None:
        return HookRegistry()
    # Plugin script paths are absolute after plugin normalize.
    return load_hook_registry_from_dict(
        merged, settings=settings, workspace_root=root, base_dir=None
    )


def run_pre_hooks(
    registry: HookRegistry,
    *,
    tool: str,
    args: dict[str, Any],
) -> PreResult:
    """Run Pre handlers in order. First deny wins. Args may be rewritten."""
    current = dict(args)
    for handler in registry.pre:
        ctx = HookContext(event="pre_tool_use", tool=tool, args=dict(current))
        try:
            out = handler(ctx)
        except Exception as exc:  # noqa: BLE001 — fail closed on Pre
            logger.exception("PreToolUse handler error tool=%s", tool)
            return PreResult(allow=False, reason=f"PreToolUse handler error: {exc}")
        if out is None or out is True:
            continue
        if out is False:
            return PreResult(allow=False, reason="PreToolUse handler returned deny")
        if isinstance(out, str):
            return PreResult(allow=False, reason=out)
        if isinstance(out, PreResult):
            if out.args is not None:
                current = dict(out.args)
            if not out.allow:
                return PreResult(allow=False, reason=out.reason, args=current)
            continue
        if isinstance(out, dict):
            current = dict(out)
            continue
        logger.warning("Ignoring unexpected PreToolUse return: %r", out)
    return PreResult(allow=True, args=current)


def run_post_hooks(
    registry: HookRegistry,
    *,
    tool: str,
    args: dict[str, Any],
    result: Any,
) -> Any:
    """Run Post handlers; each may replace the result string. Errors → keep prior."""
    current = result
    for handler in registry.post:
        ctx = HookContext(
            event="post_tool_use", tool=tool, args=dict(args), result=current
        )
        try:
            out = handler(ctx)
        except Exception:  # noqa: BLE001 — fail open on Post
            logger.exception("PostToolUse handler error tool=%s", tool)
            continue
        if out is not None:
            current = out
    return current


def run_stop_hooks(registry: HookRegistry, *, content: str | None) -> None:
    for handler in registry.stop:
        ctx = HookContext(event="stop", stop_content=content)
        try:
            handler(ctx)
        except Exception:  # noqa: BLE001
            logger.exception("Stop handler error")


def _normalize_args(kwargs: Mapping[str, Any] | dict[str, Any]) -> Any:
    if len(kwargs) == 1 and "kwargs" in kwargs and isinstance(kwargs["kwargs"], dict):
        return kwargs["kwargs"]
    return dict(kwargs)


def apply_hooks(
    tools: Sequence[BaseTool],
    registry: HookRegistry,
) -> list[BaseTool]:
    """Outer wrap: Pre → inner tool (permissions+body) → Post.

    Empty registry → return tools unchanged.
    """
    if registry.empty:
        return list(tools)
    return [_wrap_one_with_hooks(t, registry) for t in tools]


def _wrap_one_with_hooks(tool: BaseTool, registry: HookRegistry) -> BaseTool:
    name = tool.name
    description = tool.description or name
    args_schema = getattr(tool, "args_schema", None)

    def _hooked(**kwargs: Any) -> Any:
        args = _normalize_args(kwargs)
        args_dict = args if isinstance(args, dict) else {}
        pre = run_pre_hooks(registry, tool=name, args=args_dict)
        if not pre.allow:
            return hook_denied_message(name, pre.reason)
        call_args = pre.args if pre.args is not None else args_dict
        result = tool.invoke(call_args)
        return run_post_hooks(registry, tool=name, args=call_args, result=result)

    async def _ahooked(**kwargs: Any) -> Any:
        # M22: preserve ainvoke through the hook plane (Pre/Post stay sync).
        args = _normalize_args(kwargs)
        args_dict = args if isinstance(args, dict) else {}
        pre = run_pre_hooks(registry, tool=name, args=args_dict)
        if not pre.allow:
            return hook_denied_message(name, pre.reason)
        call_args = pre.args if pre.args is not None else args_dict
        result = await tool.ainvoke(call_args)
        return run_post_hooks(registry, tool=name, args=call_args, result=result)

    return StructuredTool(
        name=name,
        description=description,
        args_schema=args_schema,
        func=_hooked,
        coroutine=_ahooked,
    )
