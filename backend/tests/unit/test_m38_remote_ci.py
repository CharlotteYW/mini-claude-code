"""M38 unit tests: remote CI poll state machine, timeout, wraps, HITL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import StructuredTool

from mini_claude_code.agent.permissions import resolve_permission
from mini_claude_code.config import Settings
from mini_claude_code.tools.remote_ci import (
    PollResult,
    apply_hitl_if_needed,
    classify_check_runs,
    merge_poll_views,
    parse_pr_number,
    poll_until,
    wait_for_checks_impl,
    wrap_open_pr_with_remote_ci,
)

pytestmark = pytest.mark.unit


def test_parse_pr_number() -> None:
    assert parse_pr_number("https://github.com/acme/repo/pull/42") == 42
    assert parse_pr_number("PR created: https://github.com/a/b/pull/7\n") == 7
    assert parse_pr_number("PR #99 opened") == 99
    assert parse_pr_number("12") == 12
    assert parse_pr_number("no pr here") is None


def test_classify_check_runs() -> None:
    assert classify_check_runs([]) == "pending"
    assert (
        classify_check_runs(
            [{"name": "a", "status": "in_progress", "conclusion": None}]
        )
        == "pending"
    )
    assert (
        classify_check_runs(
            [{"name": "a", "status": "completed", "conclusion": "success"}]
        )
        == "green"
    )
    assert (
        classify_check_runs(
            [
                {"name": "a", "status": "completed", "conclusion": "success"},
                {"name": "b", "status": "completed", "conclusion": "failure"},
            ]
        )
        == "red"
    )
    assert (
        classify_check_runs(
            [{"name": "a", "status": "completed", "conclusion": "skipped"}]
        )
        == "green"
    )


def test_merge_poll_views() -> None:
    assert merge_poll_views("green", "pending") == "pending"
    assert merge_poll_views("pending", "green") == "pending"
    assert merge_poll_views("green", "red") == "red"
    assert merge_poll_views("green", None) == "green"


def test_poll_until_green() -> None:
    calls = {"n": 0}

    def fetch_once() -> tuple[str, list[dict[str, Any]], str]:
        calls["n"] += 1
        if calls["n"] < 2:
            return "pending", [{"name": "ci", "status": "in_progress"}], "abc"
        return (
            "green",
            [{"name": "ci", "status": "completed", "conclusion": "success"}],
            "abc",
        )

    sleeps: list[float] = []
    clock = {"t": 0.0}

    result = poll_until(
        fetch_once=fetch_once,
        timeout_sec=30,
        poll_sec=1,
        sleep=lambda s: sleeps.append(s),
        monotonic=lambda: clock.__setitem__("t", clock["t"] + 0.01) or clock["t"],
    )
    assert result.state == "green"
    assert result.polls == 2
    assert sleeps  # waited once between polls


def test_poll_until_red() -> None:
    def fetch_once() -> tuple[str, list[dict[str, Any]], str]:
        return (
            "red",
            [{"name": "ci", "status": "completed", "conclusion": "failure"}],
            "deadbeef",
        )

    result = poll_until(
        fetch_once=fetch_once,
        timeout_sec=10,
        poll_sec=1,
        sleep=lambda _s: None,
        monotonic=lambda: 0.0,
    )
    assert result.state == "red"
    assert result.polls == 1


def test_poll_until_timeout() -> None:
    clock = {"t": 0.0}

    def fetch_once() -> tuple[str, list[dict[str, Any]], str]:
        return "pending", [], "sha"

    def mono() -> float:
        return clock["t"]

    def sleep(sec: float) -> None:
        clock["t"] += sec

    result = poll_until(
        fetch_once=fetch_once,
        timeout_sec=3,
        poll_sec=1,
        sleep=sleep,
        monotonic=mono,
    )
    assert result.state == "timed_out"
    assert result.polls >= 2


def test_wait_skipped_when_disabled(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        SHIP_REMOTE_CI=False,
        PR_DRY_RUN=False,
        GH_TOKEN="tok",
    )
    out = wait_for_checks_impl(
        pr_number=1,
        workspace_root=tmp_path,
        settings=settings,
    )
    data = json.loads(out)
    assert data["state"] == "skipped"
    assert "SHIP_REMOTE_CI=0" in data["summary"]


def test_wait_skipped_dry_run(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        SHIP_REMOTE_CI=True,
        PR_DRY_RUN=True,
        GH_TOKEN="tok",
    )
    out = wait_for_checks_impl(
        pr_number=1,
        workspace_root=tmp_path,
        settings=settings,
    )
    assert json.loads(out)["state"] == "skipped"


def test_wait_green_with_fake_http(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        SHIP_REMOTE_CI=True,
        PR_DRY_RUN=False,
        GH_TOKEN="tok",
        SHIP_REMOTE_CI_TIMEOUT_SEC=10,
        SHIP_REMOTE_CI_POLL_SEC=0.01,
        SHIP_REMOTE_CI_HITL=False,
    )

    def http_get(url: str, token: str) -> dict[str, Any]:
        assert token == "tok"
        if "/pulls/" in url:
            return {"head": {"sha": "abc123"}}
        if "/check-runs" in url:
            return {
                "check_runs": [
                    {
                        "name": "unit",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        if url.endswith("/status"):
            return {"state": "success", "statuses": []}
        raise AssertionError(url)

    out = wait_for_checks_impl(
        pr_number=9,
        owner="acme",
        repo="demo",
        workspace_root=tmp_path,
        settings=settings,
        http_get=http_get,
        sleep=lambda _s: None,
    )
    data = json.loads(out)
    assert data["state"] == "green"
    assert data["sha"] == "abc123"


def test_hitl_on_red_reject() -> None:
    result = PollResult(state="red", summary="failed", sha="x")
    asks: list[tuple[str, dict[str, Any]]] = []

    def ask(name: str, payload: dict[str, Any]) -> bool:
        asks.append((name, payload))
        return False

    out = apply_hitl_if_needed(
        result, pr_number=3, hitl_enabled=True, ask_callback=ask
    )
    assert asks and asks[0][0] == "wait_for_checks"
    assert out.hitl_override is False
    assert "rejected" in out.summary


def test_wrap_open_pr_appends_remote_ci(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        SHIP_REMOTE_CI=True,
        PR_DRY_RUN=False,
        GH_TOKEN="tok",
        SHIP_REMOTE_CI_HITL=False,
        SHIP_REMOTE_CI_TIMEOUT_SEC=5,
        SHIP_REMOTE_CI_POLL_SEC=0.01,
    )

    def open_pr(title: str, body: str, base: str = "main", head: str | None = None) -> str:
        return "https://github.com/acme/demo/pull/11"

    def http_get(url: str, token: str) -> dict[str, Any]:
        if "/pulls/" in url:
            return {"head": {"sha": "s"}}
        if "/check-runs" in url:
            return {
                "check_runs": [
                    {"name": "ci", "status": "completed", "conclusion": "success"}
                ]
            }
        return {"state": "success", "statuses": []}

    tool = StructuredTool.from_function(
        open_pr,
        name="open_pull_request",
        description="open pr",
    )
    wrapped = wrap_open_pr_with_remote_ci(
        tool,
        workspace_root=tmp_path,
        settings=settings,
        http_get=http_get,
        sleep=lambda _s: None,
    )
    text = wrapped.invoke({"title": "t", "body": "b"})
    assert "pull/11" in text
    assert "remote_ci" in text
    assert '"state": "green"' in text or '"state": "green"' in text.replace(" ", "")


def test_wait_for_checks_permission_auto() -> None:
    assert resolve_permission("wait_for_checks", plan_mode=False) == "auto"
    assert resolve_permission("wait_for_checks", plan_mode=True) == "auto"
