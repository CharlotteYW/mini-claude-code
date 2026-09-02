"""open_pull_request tool — GH_TOKEN + dry-run default (M18)."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.config import Settings, get_settings


def _current_branch(workspace_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "HEAD"
    if completed.returncode != 0:
        return "HEAD"
    return completed.stdout.strip() or "HEAD"


def _parse_github_remote(workspace_root: Path) -> tuple[str, str] | None:
    try:
        completed = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    url = completed.stdout.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com" not in url:
        return None
    if url.startswith("git@"):
        # git@github.com:owner/repo
        path = url.split(":", 1)[-1]
    else:
        path = url.split("github.com/", 1)[-1]
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _create_pr_via_api(
    *,
    owner: str,
    repo: str,
    title: str,
    body: str,
    base: str,
    head: str,
    token: str,
) -> str:
    payload = json.dumps(
        {"title": title, "body": body, "base": base, "head": head}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "mini-claude-code",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return f"ERROR: GitHub API {exc.code}: {detail}"
    return f"PR created: {data.get('html_url', data)}"


def open_pull_request_impl(
    title: str,
    body: str,
    base: str = "main",
    head: str | None = None,
    *,
    workspace_root: Path,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    workspace = workspace_root.expanduser().resolve()
    effective_head = head or _current_branch(workspace)

    if settings.pr_dry_run:
        return json.dumps(
            {
                "dry_run": True,
                "title": title,
                "body": body,
                "base": base,
                "head": effective_head,
                "message": "PR_DRY_RUN=1 — no GitHub call made",
            },
            indent=2,
        )

    token = (settings.gh_token or "").strip()
    if not token:
        return "ERROR: live PR requires GH_TOKEN in the environment"

    # Prefer gh CLI when available (uses GH_TOKEN).
    try:
        completed = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--base",
                base,
                "--head",
                effective_head,
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env={**os.environ, "GH_TOKEN": token},
        )
    except FileNotFoundError:
        completed = None

    if completed is not None and completed.returncode == 0:
        out = completed.stdout.strip() or completed.stderr.strip()
        return out or "PR created via gh"

    remote = _parse_github_remote(workspace)
    if not remote:
        err = completed.stderr.strip() if completed else "gh not found"
        return f"ERROR: could not create PR ({err}); no parseable github.com origin"
    owner, repo = remote
    return _create_pr_via_api(
        owner=owner,
        repo=repo,
        title=title,
        body=body,
        base=base,
        head=effective_head,
        token=token,
    )


def build_github_pr_tools(
    workspace_root: Path,
    *,
    settings: Settings | None = None,
) -> list[BaseTool]:
    root = workspace_root.expanduser().resolve()
    settings = settings or get_settings()

    def open_pull_request(
        title: str,
        body: str,
        base: str = "main",
        head: str | None = None,
    ) -> str:
        """Open a GitHub pull request from the workspace repo (dry-run by default).

        Uses GH_TOKEN when PR_DRY_RUN=0. Does not git push — head must exist on remote.
        """
        return open_pull_request_impl(
            title,
            body,
            base=base,
            head=head,
            workspace_root=root,
            settings=settings,
        )

    return [
        StructuredTool.from_function(
            open_pull_request,
            name="open_pull_request",
            description=(
                "Open a GitHub pull request with title and body. "
                "Default is dry-run (PR_DRY_RUN=1). Requires GH_TOKEN for live create."
            ),
        )
    ]
