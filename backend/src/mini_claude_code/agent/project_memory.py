"""Project memory: load workspace/AGENT.md for every model turn (M8).

File-based instructions survive compaction and new thread_ids. Distinct from
Neo4j facts (structured recall) and checkpointer transcripts (M5).
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import BaseMessage, SystemMessage

AGENT_MD_NAME = "AGENT.md"

_DEFAULT_AGENT_MD = """# Project agent notes

Edit this file to give the coding agent durable project instructions.
Examples: preferred package manager, layout of this workspace, coding norms.

This file is injected every turn (M8). It is not chat history.
"""


def agent_md_path(workspace_root: Path) -> Path:
    return workspace_root.expanduser().resolve() / AGENT_MD_NAME


def ensure_agent_md(workspace_root: Path) -> Path:
    """Create a template AGENT.md if missing; return its path."""
    path = agent_md_path(workspace_root)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_AGENT_MD, encoding="utf-8")
    return path


def load_agent_md(workspace_root: Path, *, ensure: bool = True) -> str | None:
    """Return AGENT.md text, or None if missing and ensure=False."""
    path = agent_md_path(workspace_root)
    if not path.is_file():
        if not ensure:
            return None
        ensure_agent_md(workspace_root)
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def inject_project_memory(
    messages: list[BaseMessage],
    workspace_root: Path,
    *,
    ensure: bool = True,
) -> list[BaseMessage]:
    """Prepend a SystemMessage with AGENT.md if not already present.

    Idempotent for a single turn: skips if the first message is already our
    project-memory marker (avoids stacking on every tool loop iteration).
    """
    body = load_agent_md(workspace_root, ensure=ensure)
    if not body:
        return list(messages)

    marker = "[project memory: AGENT.md]"
    if messages:
        first = messages[0]
        if isinstance(first, SystemMessage) and marker in str(first.content):
            return list(messages)

    injected = SystemMessage(content=f"{marker}\n{body}")
    return [injected, *messages]
