"""Remote CI gate (M38): poll GitHub Checks after open_pull_request.

Local ``ship_check`` (M19) ≠ Actions green. Opt-in via ``SHIP_REMOTE_CI=1``.
On red / timeout: structured fail + optional HITL ``interrupt`` (not auto-fix).

Simplification: thin REST poll (check-runs + combined status); no merge queue,
no job-log scraping, no auto-repair of remote failures.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools.github_pr import _parse_github_remote

PollState = Literal["pending", "green", "red", "timed_out", "skipped"]

# Injected for unit tests.
HttpGet = Callable[[str, str], dict[str, Any]]
SleepFn = Callable[[float], None]
MonotonicFn = Callable[[], float]
AskFn = Callable[[str, dict[str, Any]], bool]

_PR_URL_RE = re.compile(
    r"https?://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)", re.IGNORECASE
)
_PR_NUM_RE = re.compile(r"(?:PR|pull request)\s*#?\s*(\d+)", re.IGNORECASE)


def parse_pr_ref(text: str) -> tuple[str | None, str | None, int | None]:
    """Return (owner, repo, number) when parseable from URL or bare number."""
    if not text:
        return None, None, None
    m = _PR_URL_RE.search(text)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    m = _PR_NUM_RE.search(text)
    if m:
        return None, None, int(m.group(1))
    stripped = text.strip()
    if stripped.isdigit():
        return None, None, int(stripped)
    return None, None, None


def parse_pr_number(text: str) -> int | None:
    """Extract a PR number from gh/API tool output or a raw URL."""
    _, _, number = parse_pr_ref(text)
    return number


_FAIL_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
)
_OK_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})


@dataclass
class PollResult:
    state: PollState
    summary: str
    sha: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    polls: int = 0
    hitl_override: bool | None = None

    def as_tool_text(self) -> str:
        payload = {
            "remote_ci": True,
            "state": self.state,
            "sha": self.sha,
            "polls": self.polls,
            "summary": self.summary,
            "checks": self.checks[:20],
        }
        if self.hitl_override is not None:
            payload["hitl_override"] = self.hitl_override
        return json.dumps(payload, indent=2)


def classify_check_runs(runs: list[dict[str, Any]]) -> PollState:
    """Aggregate check-run list → pending | green | red.

    Skipped/neutral count as OK. Empty list → pending (Actions may not have
    started yet).
    """
    if not runs:
        return "pending"
    pending = False
    for run in runs:
        status = str(run.get("status") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        if status and status != "completed":
            pending = True
            continue
        if conclusion in _FAIL_CONCLUSIONS:
            return "red"
        if conclusion and conclusion not in _OK_CONCLUSIONS:
            # unknown completed conclusion → treat as red (cautious)
            return "red"
    return "pending" if pending else "green"


def classify_combined_status(state: str | None) -> PollState | None:
    """Map legacy combined commit status; None if unused/empty."""
    if not state:
        return None
    s = state.lower()
    if s == "success":
        return "green"
    if s in {"failure", "error"}:
        return "red"
    if s == "pending":
        return "pending"
    return None


def merge_poll_views(
    check_state: PollState,
    combined: PollState | None,
) -> PollState:
    """Prefer red; else pending if either pending; else green."""
    states = [check_state]
    if combined is not None:
        states.append(combined)
    if any(s == "red" for s in states):
        return "red"
    if any(s == "pending" for s in states):
        return "pending"
    return "green"


def github_api_get(url: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "mini-claude-code",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc


def fetch_pr_head_sha(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    *,
    http_get: HttpGet | None = None,
) -> str:
    getter = http_get or github_api_get
    data = getter(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
        token,
    )
    sha = ((data.get("head") or {}).get("sha")) or ""
    if not sha:
        raise RuntimeError(f"PR #{pr_number} missing head.sha")
    return str(sha)


def fetch_checks_snapshot(
    owner: str,
    repo: str,
    sha: str,
    token: str,
    *,
    http_get: HttpGet | None = None,
) -> tuple[PollState, list[dict[str, Any]]]:
    """Return (aggregated state, normalized check rows)."""
    getter = http_get or github_api_get
    runs_payload = getter(
        f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs"
        f"?per_page=100",
        token,
    )
    raw_runs = runs_payload.get("check_runs") or []
    if not isinstance(raw_runs, list):
        raw_runs = []
    normalized: list[dict[str, Any]] = []
    for run in raw_runs:
        if not isinstance(run, dict):
            continue
        normalized.append(
            {
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
            }
        )
    check_state = classify_check_runs(normalized)

    combined: PollState | None = None
    try:
        status_payload = getter(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/status",
            token,
        )
        combined = classify_combined_status(
            str(status_payload.get("state") or "") or None
        )
        # If combined reports statuses but check-runs empty, surface them.
        if not normalized:
            for st in status_payload.get("statuses") or []:
                if isinstance(st, dict):
                    normalized.append(
                        {
                            "name": st.get("context"),
                            "status": "completed"
                            if st.get("state") not in (None, "pending")
                            else "in_progress",
                            "conclusion": st.get("state"),
                        }
                    )
            if normalized and check_state == "pending" and combined:
                check_state = combined
    except RuntimeError:
        # Combined status optional when check-runs work.
        pass

    return merge_poll_views(check_state, combined), normalized


def poll_until(
    *,
    fetch_once: Callable[[], tuple[PollState, list[dict[str, Any]], str]],
    timeout_sec: float,
    poll_sec: float,
    sleep: SleepFn = time.sleep,
    monotonic: MonotonicFn = time.monotonic,
) -> PollResult:
    """Poll until green/red or timeout. ``fetch_once`` → (state, checks, sha)."""
    deadline = monotonic() + max(0.0, timeout_sec)
    polls = 0
    last_checks: list[dict[str, Any]] = []
    sha = ""
    while True:
        polls += 1
        state, checks, sha = fetch_once()
        last_checks = checks
        if state == "green":
            return PollResult(
                state="green",
                summary="Remote CI green (required checks succeeded).",
                sha=sha,
                checks=last_checks,
                polls=polls,
            )
        if state == "red":
            return PollResult(
                state="red",
                summary="Remote CI red (one or more checks failed).",
                sha=sha,
                checks=last_checks,
                polls=polls,
            )
        now = monotonic()
        if now >= deadline:
            return PollResult(
                state="timed_out",
                summary=(
                    f"Remote CI timed out after {timeout_sec:.0f}s "
                    f"({polls} poll(s)); still pending or no checks observed."
                ),
                sha=sha,
                checks=last_checks,
                polls=polls,
            )
        sleep(min(poll_sec, max(0.0, deadline - now)))


def _hitl_payload(result: PollResult, *, pr_number: int) -> dict[str, Any]:
    return {
        "type": "remote_ci_gate",
        "tool": "wait_for_checks",
        "pr_number": pr_number,
        "state": result.state,
        "summary": result.summary,
        "question": (
            f"Remote CI is {result.state}. Approve to proceed anyway "
            "(not recommended), or reject to stop the ship flow."
        ),
    }


def apply_hitl_if_needed(
    result: PollResult,
    *,
    pr_number: int,
    hitl_enabled: bool,
    ask_callback: AskFn | None = None,
) -> PollResult:
    """On red/timeout, optional interrupt/ask; override does not flip to green."""
    if result.state not in {"red", "timed_out"} or not hitl_enabled:
        return result
    payload = _hitl_payload(result, pr_number=pr_number)
    if ask_callback is not None:
        approved = bool(ask_callback("wait_for_checks", payload))
    else:
        approved = bool(interrupt(payload))
    result.hitl_override = approved
    if approved:
        result.summary = (
            f"{result.summary} HITL override=approved — human accepted risk."
        )
    else:
        result.summary = (
            f"{result.summary} HITL override=rejected — do not claim ship success."
        )
    return result


def wait_for_checks_impl(
    *,
    pr_number: int | None = None,
    pr_url_or_text: str | None = None,
    owner: str | None = None,
    repo: str | None = None,
    workspace_root: Path | None = None,
    settings: Settings | None = None,
    http_get: HttpGet | None = None,
    sleep: SleepFn = time.sleep,
    monotonic: MonotonicFn = time.monotonic,
    ask_callback: AskFn | None = None,
) -> str:
    """Poll remote checks for a PR; return JSON summary for the model."""
    settings = settings or get_settings()
    if not settings.ship_remote_ci:
        return PollResult(
            state="skipped",
            summary="SHIP_REMOTE_CI=0 — remote wait skipped.",
        ).as_tool_text()

    if settings.pr_dry_run:
        return PollResult(
            state="skipped",
            summary="PR_DRY_RUN=1 — no live PR/checks to poll; remote wait skipped.",
        ).as_tool_text()

    token = (settings.gh_token or "").strip()
    if not token:
        return PollResult(
            state="skipped",
            summary="ERROR: wait_for_checks needs GH_TOKEN when SHIP_REMOTE_CI=1.",
        ).as_tool_text()

    number = pr_number
    url_owner = url_repo = None
    if pr_url_or_text:
        o, r, n = parse_pr_ref(pr_url_or_text)
        url_owner, url_repo = o, r
        if number is None:
            number = n
    if number is None:
        return PollResult(
            state="skipped",
            summary="ERROR: provide pr_number or text containing a GitHub PR URL.",
        ).as_tool_text()

    if not owner or not repo:
        owner = owner or url_owner
        repo = repo or url_repo
    if not owner or not repo:
        if workspace_root is None:
            return PollResult(
                state="skipped",
                summary="ERROR: owner/repo or workspace_root required.",
            ).as_tool_text()
        remote = _parse_github_remote(workspace_root)
        if not remote:
            return PollResult(
                state="skipped",
                summary="ERROR: could not parse github.com origin from workspace.",
            ).as_tool_text()
        owner, repo = remote

    def fetch_once() -> tuple[PollState, list[dict[str, Any]], str]:
        sha = fetch_pr_head_sha(
            owner, repo, number, token, http_get=http_get
        )
        state, checks = fetch_checks_snapshot(
            owner, repo, sha, token, http_get=http_get
        )
        return state, checks, sha

    try:
        result = poll_until(
            fetch_once=fetch_once,
            timeout_sec=float(settings.ship_remote_ci_timeout_sec),
            poll_sec=float(settings.ship_remote_ci_poll_sec),
            sleep=sleep,
            monotonic=monotonic,
        )
    except Exception as exc:  # noqa: BLE001 — surface to agent
        return PollResult(
            state="skipped",
            summary=f"ERROR: remote CI poll failed: {exc}",
        ).as_tool_text()

    result = apply_hitl_if_needed(
        result,
        pr_number=number,
        hitl_enabled=bool(settings.ship_remote_ci_hitl),
        ask_callback=ask_callback,
    )
    return result.as_tool_text()


def wrap_open_pr_with_remote_ci(
    tool: BaseTool,
    *,
    workspace_root: Path,
    settings: Settings,
    ask_callback: AskFn | None = None,
    http_get: HttpGet | None = None,
    sleep: SleepFn = time.sleep,
    monotonic: MonotonicFn = time.monotonic,
) -> BaseTool:
    """After a live PR create, optionally poll Checks when SHIP_REMOTE_CI=1."""
    if tool.name != "open_pull_request":
        return tool
    original = tool

    def _wrapped(**kwargs: Any) -> str:
        out = original.invoke(kwargs)
        text = out if isinstance(out, str) else str(out)
        if not settings.ship_remote_ci:
            return text
        if settings.pr_dry_run or text.startswith("SHIP_GATE:"):
            return text
        if text.startswith("ERROR:"):
            return text
        pr_owner, pr_repo, pr_n = parse_pr_ref(text)
        if pr_n is None:
            return (
                text
                + "\n\n[remote_ci] SHIP_REMOTE_CI=1 but no PR number parsed; "
                "call wait_for_checks manually with pr_number."
            )
        remote = wait_for_checks_impl(
            pr_number=pr_n,
            pr_url_or_text=text,
            owner=pr_owner,
            repo=pr_repo,
            workspace_root=workspace_root,
            settings=settings,
            http_get=http_get,
            sleep=sleep,
            monotonic=monotonic,
            ask_callback=ask_callback,
        )
        return text + "\n\n=== remote_ci (auto after open_pull_request) ===\n" + remote

    return StructuredTool.from_function(
        _wrapped,
        name=original.name,
        description=original.description,
        args_schema=getattr(original, "args_schema", None),
    )


def build_remote_ci_tools(
    workspace_root: Path,
    *,
    settings: Settings | None = None,
    ask_callback: AskFn | None = None,
    http_get: HttpGet | None = None,
) -> list[BaseTool]:
    """Register ``wait_for_checks`` (no-op JSON when SHIP_REMOTE_CI=0)."""
    root = workspace_root.expanduser().resolve()
    settings = settings or get_settings()

    def wait_for_checks(
        pr_number: int | None = None,
        pr_url_or_text: str | None = None,
    ) -> str:
        """Poll GitHub Checks for a PR until green, red, or timeout (M38).

        Requires SHIP_REMOTE_CI=1 and GH_TOKEN. On red/timeout, may HITL-interrupt
        when SHIP_REMOTE_CI_HITL=1. Does not auto-fix CI.
        """
        return wait_for_checks_impl(
            pr_number=pr_number,
            pr_url_or_text=pr_url_or_text,
            workspace_root=root,
            settings=settings,
            http_get=http_get,
            ask_callback=ask_callback,
        )

    return [
        StructuredTool.from_function(
            wait_for_checks,
            name="wait_for_checks",
            description=(
                "Poll GitHub Actions/Checks for a pull request (opt-in SHIP_REMOTE_CI). "
                "Pass pr_number or pr_url_or_text. Returns JSON state: "
                "green|red|timed_out|skipped. HITL on red/timeout when enabled."
            ),
        )
    ]
