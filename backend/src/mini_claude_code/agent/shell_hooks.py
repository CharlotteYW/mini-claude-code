"""Shell/script hook runners (M24).

Industry-style: JSON on stdin → JSON (or exit code) on stdout.
Deny-by-default: requires ``HOOK_SHELL_ENABLED`` + allowlist / plugin-path check.
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mini_claude_code.config import Settings

if TYPE_CHECKING:
    from mini_claude_code.agent.hooks import HookContext, PreResult

logger = logging.getLogger(__name__)


def parse_allowlist(raw: str) -> list[Path]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return [Path(p).expanduser().resolve() for p in parts]


def is_path_allowed(
    target: Path,
    *,
    settings: Settings,
    workspace_root: Path | None = None,
) -> bool:
    """Allow if exact/prefix match on allowlist, or under workspace/plugins/."""
    resolved = target.expanduser().resolve()
    for allowed in parse_allowlist(settings.hook_shell_allowlist):
        if resolved == allowed or _is_relative_to(resolved, allowed):
            return True
    if workspace_root is not None:
        plugins_root = (workspace_root.expanduser().resolve() / "plugins").resolve()
        if _is_relative_to(resolved, plugins_root):
            return True
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_script_argv(
    entry: dict[str, Any],
    *,
    base_dir: Path | None,
) -> list[str]:
    """Build argv for a shell/script hook entry."""
    import sys

    typ = str(entry.get("type") or "").strip().lower()
    if typ == "script":
        raw_path = entry.get("path")
        if not raw_path:
            raise ValueError("script hook requires path")
        path = Path(str(raw_path))
        if not path.is_absolute():
            if base_dir is None:
                raise ValueError(f"relative script path needs base_dir: {raw_path}")
            path = (base_dir / path).resolve()
        else:
            path = path.resolve()
        if path.suffix == ".py":
            return [sys.executable, str(path)]
        return [str(path)]
    if typ == "shell":
        cmd = entry.get("command")
        if isinstance(cmd, list):
            argv = [str(c) for c in cmd]
            if not argv:
                raise ValueError("shell hook command list is empty")
            return argv
        if isinstance(cmd, str) and cmd.strip():
            return shlex.split(cmd)
        raise ValueError("shell hook requires command string or list")
    raise ValueError(f"unknown hook type {typ!r}")


def run_shell_hook(
    argv: list[str],
    payload: dict[str, Any],
    *,
    timeout_sec: float,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    """Run subprocess; return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        argv,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def parse_pre_stdout(stdout: str, *, returncode: int) -> PreResult:
    """Interpret shell Pre hook stdout / exit code."""
    from mini_claude_code.agent.hooks import PreResult

    text = stdout.strip()
    if returncode != 0 and not text:
        return PreResult(
            allow=False,
            reason=f"shell Pre hook exited {returncode} with empty stdout",
        )
    if not text:
        # exit 0 + empty → allow
        if returncode == 0:
            return PreResult(allow=True)
        return PreResult(allow=False, reason=f"shell Pre hook exited {returncode}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if returncode != 0:
            return PreResult(allow=False, reason=text[:200])
        # Non-JSON success → allow, ignore body
        return PreResult(allow=True)
    if not isinstance(data, dict):
        return PreResult(allow=False, reason="shell Pre hook JSON must be an object")
    allow = data.get("allow", returncode == 0)
    if isinstance(allow, str):
        allow = allow.lower() in ("1", "true", "yes")
    reason = data.get("reason")
    args = data.get("args")
    if args is not None and not isinstance(args, dict):
        return PreResult(allow=False, reason="shell Pre hook args must be an object")
    if not allow or returncode != 0:
        return PreResult(
            allow=False,
            reason=str(reason) if reason else f"shell Pre hook denied (exit {returncode})",
            args=dict(args) if isinstance(args, dict) else None,
        )
    return PreResult(
        allow=True,
        reason=str(reason) if reason else None,
        args=dict(args) if isinstance(args, dict) else None,
    )


def parse_post_stdout(stdout: str, *, prior: Any) -> Any:
    """Interpret shell Post hook stdout; empty → keep prior."""
    text = stdout.strip()
    if not text:
        return prior
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    if isinstance(data, str):
        return data
    return text


def make_shell_pre_handler(
    argv: list[str],
    *,
    settings: Settings,
    label: str,
    cwd: Path | None = None,
) -> Any:
    from mini_claude_code.agent.hooks import HookContext, PreResult

    def _pre(ctx: HookContext) -> PreResult:
        payload = {
            "event": "pre_tool_use",
            "tool": ctx.tool,
            "args": dict(ctx.args or {}),
        }
        try:
            code, out, err = run_shell_hook(
                argv,
                payload,
                timeout_sec=settings.hook_shell_timeout_sec,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return PreResult(allow=False, reason=f"shell Pre hook timed out ({label})")
        except OSError as exc:
            return PreResult(allow=False, reason=f"shell Pre hook spawn failed: {exc}")
        if err.strip():
            logger.debug("shell Pre hook stderr label=%s: %s", label, err[:300])
        return parse_pre_stdout(out, returncode=code)

    _pre.__name__ = f"shell_pre:{label}"
    return _pre


def make_shell_post_handler(
    argv: list[str],
    *,
    settings: Settings,
    label: str,
    cwd: Path | None = None,
) -> Any:
    from mini_claude_code.agent.hooks import HookContext

    def _post(ctx: HookContext) -> str | None:
        payload = {
            "event": "post_tool_use",
            "tool": ctx.tool,
            "args": dict(ctx.args or {}),
            "result": ctx.result
            if isinstance(ctx.result, (str, int, float, bool, type(None)))
            else str(ctx.result),
        }
        try:
            code, out, err = run_shell_hook(
                argv,
                payload,
                timeout_sec=settings.hook_shell_timeout_sec,
                cwd=cwd,
            )
        except (subprocess.TimeoutExpired, OSError):
            logger.exception("shell Post hook failed label=%s", label)
            return None
        if code != 0:
            logger.warning(
                "shell Post hook exit=%s label=%s; keeping prior result", code, label
            )
            return None
        if err.strip():
            logger.debug("shell Post hook stderr label=%s: %s", label, err[:300])
        new = parse_post_stdout(out, prior=ctx.result)
        if new is ctx.result:
            return None
        return new if isinstance(new, str) else str(new)

    _post.__name__ = f"shell_post:{label}"
    return _post
