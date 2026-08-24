"""Structured git tools via subprocess (M4).

Why dedicated tools instead of only run_shell("git ..."):
- Clearer JSON schemas for the model (message, path limits, etc.)
- Easier unit tests without parsing free-form shell
- Same underlying mechanism: still calls the `git` binary (subprocess)

Alternatives: GitPython / pygit2 — avoid for now so behavior matches CLI git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

MAX_OUTPUT_CHARS = 20_000
GIT_TIMEOUT_SEC = 30


def _run_git(workspace_root: Path, args: list[str]) -> str:
    root = workspace_root.expanduser().resolve()
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        return "ERROR: git binary not found on PATH"
    except subprocess.TimeoutExpired:
        return f"ERROR: git timed out after {GIT_TIMEOUT_SEC}s"
    except OSError as exc:
        return f"ERROR: {exc}"

    parts = [f"exit_code={completed.returncode}"]
    if completed.stdout.strip():
        parts.append(completed.stdout.rstrip())
    if completed.stderr.strip():
        parts.append("stderr:\n" + completed.stderr.rstrip())
    text = "\n".join(parts)
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n... truncated after {MAX_OUTPUT_CHARS} chars"
    return text


def build_git_tools(workspace_root: Path) -> list[BaseTool]:
    root = workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    def git_status() -> str:
        """Show git status for the workspace repository."""
        return _run_git(root, ["status", "--short", "--branch"])

    def git_diff(staged: bool = False) -> str:
        """Show git diff (optionally staged)."""
        args = ["diff", "--staged"] if staged else ["diff"]
        return _run_git(root, args)

    def git_log(max_count: int = 5) -> str:
        """Show recent commits (oneline)."""
        n = max(1, min(int(max_count), 50))
        return _run_git(root, ["log", f"-{n}", "--oneline", "--decorate"])

    def git_commit(message: str) -> str:
        """Stage all changes (git add -A) and commit with the given message.

        Simplification: always stages everything. Production agents usually
        stage selectively and require human approval before commit.
        """
        if not message or not message.strip():
            return "ERROR: commit message must be non-empty"
        add = _run_git(root, ["add", "-A"])
        if add.startswith("ERROR:"):
            return add
        return _run_git(root, ["commit", "-m", message.strip()])

    return [
        StructuredTool.from_function(
            git_status,
            name="git_status",
            description="Show short git status for the workspace repo.",
        ),
        StructuredTool.from_function(
            git_diff,
            name="git_diff",
            description="Show git diff; set staged=true for staged changes only.",
        ),
        StructuredTool.from_function(
            git_log,
            name="git_log",
            description="Show recent git commits (oneline).",
        ),
        StructuredTool.from_function(
            git_commit,
            name="git_commit",
            description=(
                "Stage all changes and create a git commit with the given message. "
                "Does not push."
            ),
        ),
    ]
