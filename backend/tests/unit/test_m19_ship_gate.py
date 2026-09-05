"""M19 unit tests: ship_check, gate, SHIP_MODE."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mini_claude_code.agent.permissions import resolve_permission
from mini_claude_code.config import Settings
from mini_claude_code.tools.github_pr import build_github_pr_tools
from mini_claude_code.tools.ship import (
    ShipGate,
    apply_ship_gate_to_tools,
    build_ship_tools,
    ship_check_impl,
    ship_gate_from_settings,
)

pytestmark = pytest.mark.unit


def test_ship_check_pass_updates_gate(tmp_path: Path) -> None:
    gate = ShipGate(require_green=True, max_fix_iters=3)

    def fmt(_root: Path) -> tuple[int, str]:
        return 0, "format ok"

    def tests(_root: Path) -> tuple[int, str]:
        return 0, "tests ok"

    out = ship_check_impl(
        project_root=tmp_path,
        gate=gate,
        format_runner=fmt,
        test_runner=tests,
    )
    assert gate.last_passed is True
    assert gate.consecutive_fails == 0
    assert '"ok": true' in out or '"ok": True' in out
    data = json.loads(out.split("\n\n")[0])
    assert data["ok"] is True


def test_ship_check_fail_and_budget(tmp_path: Path) -> None:
    gate = ShipGate(require_green=True, max_fix_iters=2)

    def fmt(_root: Path) -> tuple[int, str]:
        return 1, "format bad"

    def tests(_root: Path) -> tuple[int, str]:
        return 0, "tests ok"

    ship_check_impl(
        project_root=tmp_path, gate=gate, format_runner=fmt, test_runner=tests
    )
    assert gate.last_passed is False
    assert gate.consecutive_fails == 1
    out2 = ship_check_impl(
        project_root=tmp_path, gate=gate, format_runner=fmt, test_runner=tests
    )
    assert gate.budget_exhausted()
    assert "SHIP_BUDGET_EXHAUSTED" in out2 or "budget_exhausted" in out2


def test_open_pr_blocked_until_green(tmp_path: Path) -> None:
    gate = ShipGate(require_green=True)
    tools = apply_ship_gate_to_tools(
        build_github_pr_tools(tmp_path, settings=Settings(pr_dry_run=True)),
        gate,
    )
    pr = next(t for t in tools if t.name == "open_pull_request")
    blocked = pr.invoke({"title": "t", "body": "b"})
    assert "SHIP_GATE" in blocked

    gate.record_result(True, "pass")
    ok = pr.invoke({"title": "t", "body": "b"})
    assert "dry_run" in ok


def test_require_green_off_allows_pr(tmp_path: Path) -> None:
    gate = ShipGate(require_green=False)
    tools = apply_ship_gate_to_tools(
        build_github_pr_tools(tmp_path, settings=Settings(pr_dry_run=True)),
        gate,
    )
    pr = next(t for t in tools if t.name == "open_pull_request")
    out = pr.invoke({"title": "t", "body": "b"})
    assert "dry_run" in out


def test_ship_mode_push_registers_git_push(tmp_path: Path) -> None:
    settings = Settings(ship_mode="push", ship_require_green=True)
    tools, gate = build_ship_tools(tmp_path, settings=settings)
    names = {t.name for t in tools}
    assert "ship_check" in names
    assert "git_push" in names
    assert gate.mode == "push"

    tools_pr, gate_pr = build_ship_tools(
        tmp_path, settings=Settings(ship_mode="pr")
    )
    assert "git_push" not in {t.name for t in tools_pr}
    assert gate_pr.mode == "pr"


def test_ship_gate_from_settings_invalid_mode() -> None:
    gate = ship_gate_from_settings(Settings(ship_mode="nope"))
    assert gate.mode == "pr"


def test_permissions_ship_check_auto_git_push_ask() -> None:
    assert resolve_permission("ship_check", plan_mode=False) == "auto"
    assert resolve_permission("ship_check", plan_mode=True) == "auto"
    assert resolve_permission("git_push", plan_mode=False) == "ask"
    assert resolve_permission("git_push", plan_mode=True) == "deny"
