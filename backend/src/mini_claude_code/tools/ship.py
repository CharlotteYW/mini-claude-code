"""Pre-ship quality gate (M19): ship_check + gate open_pull_request / optional push.

Simplification: local ruff + pytest only — no GitHub Actions wait.
Ship checks run against the **repo root** (this learning project), not the
agent workspace jail (workspace/ is for coding demos).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.config import Settings, get_settings, repo_root

ShipMode = Literal["pr", "push"]

# Injected runners for unit tests: (cwd) -> (exit_code, log_text)
CheckRunner = Callable[[Path], tuple[int, str]]


@dataclass
class ShipGate:
    """Shared state across ship_check and gated ship tools for one agent run."""

    require_green: bool = True
    max_fix_iters: int = 3
    mode: ShipMode = "pr"
    last_passed: bool = False
    consecutive_fails: int = 0
    check_count: int = 0
    history: list[str] = field(default_factory=list)

    def record_result(self, passed: bool, summary: str) -> None:
        self.check_count += 1
        self.last_passed = passed
        self.history.append(summary)
        if passed:
            self.consecutive_fails = 0
        else:
            self.consecutive_fails += 1

    def budget_exhausted(self) -> bool:
        return self.consecutive_fails >= max(1, self.max_fix_iters)

    def allow_open_pr(self) -> tuple[bool, str]:
        if not self.require_green:
            return True, ""
        if self.last_passed:
            return True, ""
        if self.check_count == 0:
            return False, (
                "SHIP_GATE: open_pull_request blocked — run ship_check first "
                "and get a green result (SHIP_REQUIRE_GREEN=1)."
            )
        return False, (
            "SHIP_GATE: open_pull_request blocked — last ship_check failed. "
            "Fix issues and re-run ship_check until green."
        )


def ship_gate_from_settings(settings: Settings | None = None) -> ShipGate:
    settings = settings or get_settings()
    mode = (settings.ship_mode or "pr").strip().lower()
    if mode not in ("pr", "push"):
        mode = "pr"
    return ShipGate(
        require_green=bool(settings.ship_require_green),
        max_fix_iters=max(1, int(settings.ship_max_fix_iters)),
        mode=mode,  # type: ignore[arg-type]
    )


def _run_cmd(
    args: list[str],
    *,
    cwd: Path,
    timeout_sec: int = 300,
) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"ERROR: command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"ERROR: timed out after {timeout_sec}s: {' '.join(args)}"
    except OSError as exc:
        return 1, f"ERROR: {exc}"
    parts = [f"$ {' '.join(args)}", f"exit_code={completed.returncode}"]
    if completed.stdout.strip():
        parts.append(completed.stdout.rstrip())
    if completed.stderr.strip():
        parts.append("stderr:\n" + completed.stderr.rstrip())
    return completed.returncode, "\n".join(parts)


def default_format_runner(project_root: Path) -> tuple[int, str]:
    """ruff format --check then ruff check under backend/."""
    backend = project_root / "backend"
    cwd = backend if backend.is_dir() else project_root
    code1, log1 = _run_cmd(
        ["uv", "run", "ruff", "format", "--check", "src", "tests"],
        cwd=cwd,
        timeout_sec=120,
    )
    code2, log2 = _run_cmd(
        ["uv", "run", "ruff", "check", "src", "tests"],
        cwd=cwd,
        timeout_sec=120,
    )
    return (0 if code1 == 0 and code2 == 0 else 1), log1 + "\n\n" + log2


def default_test_runner(project_root: Path) -> tuple[int, str]:
    backend = project_root / "backend"
    cwd = backend if backend.is_dir() else project_root
    return _run_cmd(
        ["uv", "run", "pytest", "-m", "unit", "-q"],
        cwd=cwd,
        timeout_sec=600,
    )


def ship_check_impl(
    *,
    project_root: Path | None = None,
    gate: ShipGate | None = None,
    format_runner: CheckRunner | None = None,
    test_runner: CheckRunner | None = None,
    skip_format: bool = False,
) -> str:
    """Run format + unit tests; update gate; return JSON-ish summary for the model."""
    root = (project_root or repo_root()).expanduser().resolve()
    gate = gate or ShipGate()
    format_runner = format_runner or default_format_runner
    test_runner = test_runner or default_test_runner

    logs: list[str] = []
    passed = True

    if not skip_format:
        f_code, f_log = format_runner(root)
        logs.append("=== format (ruff) ===\n" + f_log)
        if f_code != 0:
            passed = False

    t_code, t_log = test_runner(root)
    logs.append("=== tests (pytest -m unit) ===\n" + t_log)
    if t_code != 0:
        passed = False

    body = "\n\n".join(logs)
    if len(body) > 8000:
        body = body[:8000] + "\n… (truncated)"

    gate.record_result(passed, "pass" if passed else "fail")

    payload: dict[str, Any] = {
        "ok": passed,
        "project_root": str(root),
        "check_count": gate.check_count,
        "consecutive_fails": gate.consecutive_fails,
        "max_fix_iters": gate.max_fix_iters,
        "last_passed": gate.last_passed,
    }
    if not passed and gate.budget_exhausted():
        payload["budget_exhausted"] = True
        payload["advice"] = (
            "SHIP_BUDGET_EXHAUSTED: too many consecutive failed ship_check runs. "
            "Stop and report remaining failures to the user instead of looping."
        )
    elif not passed:
        payload["advice"] = (
            "Fix the failures with edit_file / other tools, then call ship_check again. "
            f"Fails so far this streak: {gate.consecutive_fails}/{gate.max_fix_iters}."
        )
    else:
        payload["advice"] = (
            "Green. You may call open_pull_request (still respects PR_DRY_RUN). "
            + (
                "SHIP_MODE=push also allows git_push after HITL ask."
                if gate.mode == "push"
                else "SHIP_MODE=pr — do not git push."
            )
        )

    return json.dumps(payload, indent=2) + "\n\n" + body


def wrap_tool_with_ship_gate(tool: BaseTool, gate: ShipGate) -> BaseTool:
    """Block open_pull_request when SHIP_REQUIRE_GREEN and last check was not green."""
    if tool.name != "open_pull_request":
        return tool
    original = tool

    def _gated(**kwargs: Any) -> str:
        ok, reason = gate.allow_open_pr()
        if not ok:
            return reason
        return original.invoke(kwargs)

    return StructuredTool.from_function(
        _gated,
        name=original.name,
        description=original.description,
        args_schema=getattr(original, "args_schema", None),
    )


def apply_ship_gate_to_tools(tools: list[BaseTool], gate: ShipGate) -> list[BaseTool]:
    return [wrap_tool_with_ship_gate(t, gate) for t in tools]


def git_push_impl(
    *,
    workspace_root: Path,
    gate: ShipGate,
    remote: str = "origin",
    branch: str | None = None,
) -> str:
    """Push current branch — never force. Only when SHIP_MODE=push and gate green."""
    if gate.mode != "push":
        return (
            "ERROR: git_push disabled unless SHIP_MODE=push "
            f"(current SHIP_MODE={gate.mode!r}). Prefer open_pull_request."
        )
    ok, reason = gate.allow_open_pr()
    if not ok:
        return reason.replace("open_pull_request", "git_push")

    root = workspace_root.expanduser().resolve()
    if branch:
        head = branch
    else:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            return f"ERROR: {exc}"
        if completed.returncode != 0:
            return completed.stderr.strip() or "ERROR: could not resolve HEAD"
        head = completed.stdout.strip() or "HEAD"

    code, log = _run_cmd(
        ["git", "push", "-u", remote, head],
        cwd=root,
        timeout_sec=120,
    )
    if code != 0:
        return f"ERROR: git push failed\n{log}"
    return log


def build_ship_tools(
    workspace_root: Path,
    *,
    settings: Settings | None = None,
    gate: ShipGate | None = None,
    format_runner: CheckRunner | None = None,
    test_runner: CheckRunner | None = None,
    project_root: Path | None = None,
) -> tuple[list[BaseTool], ShipGate]:
    """Return (ship tools, gate). Gate is shared with PR wrap in build_default_tools."""
    settings = settings or get_settings()
    gate = gate or ship_gate_from_settings(settings)
    root = workspace_root.expanduser().resolve()
    proj = (project_root or repo_root()).expanduser().resolve()

    def ship_check() -> str:
        """Run local pre-ship checks: ruff format/check + pytest unit tests.

        On failure, fix the code and call again (bounded by SHIP_MAX_FIX_ITERS).
        A green result is required before open_pull_request when SHIP_REQUIRE_GREEN=1.
        Checks the mini-claude-code repo root, not the agent workspace folder.
        """
        return ship_check_impl(
            project_root=proj,
            gate=gate,
            format_runner=format_runner,
            test_runner=test_runner,
        )

    tools: list[BaseTool] = [
        StructuredTool.from_function(
            ship_check,
            name="ship_check",
            description=(
                "Run local quality gate (ruff + unit tests) before opening a PR. "
                "Returns ok/fail JSON plus logs. Fix failures and re-run until green."
            ),
        )
    ]

    if gate.mode == "push":

        def git_push(remote: str = "origin", branch: str | None = None) -> str:
            """Push the current branch to remote (never force). Requires SHIP_MODE=push + green ship_check."""
            return git_push_impl(
                workspace_root=root,
                gate=gate,
                remote=remote,
                branch=branch,
            )

        tools.append(
            StructuredTool.from_function(
                git_push,
                name="git_push",
                description=(
                    "git push -u to remote (no --force). Only when SHIP_MODE=push "
                    "and ship_check is green. Prefer open_pull_request for normal ships."
                ),
            )
        )

    return tools, gate
