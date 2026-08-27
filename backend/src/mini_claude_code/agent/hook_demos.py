"""Demo lifecycle hook handlers (M15 teaching).

Referenced by id from hooks.yaml — not a plugin marketplace.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from mini_claude_code.agent.hooks import HookContext, PreResult

logger = logging.getLogger(__name__)

# Substrings that demo Pre hook blocks inside run_shell.command
FORBIDDEN_SHELL_SUBSTRINGS = ("rm -rf /", ":(){", "mkfs")


def block_dangerous_shell(ctx: HookContext) -> PreResult | dict[str, Any] | None:
    """PreToolUse: deny run_shell when command contains a forbidden substring."""
    if ctx.tool != "run_shell":
        return None
    command = str((ctx.args or {}).get("command", ""))
    for bad in FORBIDDEN_SHELL_SUBSTRINGS:
        if bad in command:
            return PreResult(
                allow=False,
                reason=f"demo hook blocked substring {bad!r} in run_shell",
            )
    return None


def append_audit_marker(ctx: HookContext) -> str | None:
    """PostToolUse: append a visible audit tag to string results."""
    if ctx.result is None:
        return None
    text = str(ctx.result)
    if "[hook:audited]" in text:
        return None
    return f"{text}\n[hook:audited]"


_SECRET_RE = re.compile(r"(SECRET|API_KEY)=(\S+)", re.IGNORECASE)


def redact_secret_pattern(ctx: HookContext) -> str | None:
    """PostToolUse: redact naive SECRET=/API_KEY= values in tool output."""
    if ctx.result is None:
        return None
    text = str(ctx.result)
    redacted, n = _SECRET_RE.subn(r"\1=***", text)
    return redacted if n else None


def log_stop(ctx: HookContext) -> None:
    """Stop: log that the turn ended without further tool_calls."""
    preview = (ctx.stop_content or "")[:120]
    logger.info("Stop hook: turn ended final_preview=%r", preview)


DEMO_PRE_HANDLERS = {
    "block_dangerous_shell": block_dangerous_shell,
}
DEMO_POST_HANDLERS = {
    "append_audit_marker": append_audit_marker,
    "redact_secret_pattern": redact_secret_pattern,
}
DEMO_STOP_HANDLERS = {
    "log_stop": log_stop,
}
