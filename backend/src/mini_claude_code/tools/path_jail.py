"""Workspace path jail for filesystem tools (M3).

All agent file paths must resolve under WORKSPACE_ROOT. This is the cheap
host-local stand-in for sandboxing; M11 replaces execution isolation, but
path jail remains useful even inside a container.
"""

from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a user path would leave the workspace root."""


def resolve_in_workspace(workspace_root: Path, user_path: str) -> Path:
    """Resolve `user_path` under `workspace_root` or raise PathEscapeError."""
    root = workspace_root.expanduser().resolve()
    raw = Path(user_path).expanduser()
    candidate = (raw if raw.is_absolute() else (root / raw)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathEscapeError(
            f"path escapes workspace root ({root}): {user_path!r}"
        ) from exc
    return candidate
