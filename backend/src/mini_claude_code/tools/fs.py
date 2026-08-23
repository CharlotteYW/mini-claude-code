"""Workspace-scoped filesystem tools for the coding agent (M3).

Topology stays call_model ↔ ToolNode; capability grows by registering these
tools. Edits use unique old_str → new_str (reviewable, cheaper than full rewrites).
"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.tools.path_jail import PathEscapeError, resolve_in_workspace

# Soft cap so a huge file does not blow the context window in one read.
MAX_READ_CHARS = 100_000
MAX_GREP_HITS = 50
MAX_GLOB_HITS = 200


def build_coding_tools(workspace_root: Path) -> list[BaseTool]:
    """Return FS tools closed over a concrete workspace root (path jail)."""
    root = workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    def read_file(path: str) -> str:
        """Read a UTF-8 text file under the workspace root."""
        try:
            target = resolve_in_workspace(root, path)
            if not target.exists():
                return f"ERROR: file not found: {path}"
            if not target.is_file():
                return f"ERROR: not a file: {path}"
            text = target.read_text(encoding="utf-8")
            if len(text) > MAX_READ_CHARS:
                return (
                    text[:MAX_READ_CHARS]
                    + f"\n\n... truncated after {MAX_READ_CHARS} characters"
                )
            return text
        except (PathEscapeError, OSError, UnicodeDecodeError) as exc:
            return f"ERROR: {exc}"

    def write_file(path: str, content: str) -> str:
        """Create or overwrite a UTF-8 text file under the workspace root."""
        try:
            target = resolve_in_workspace(root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} characters to {path}"
        except (PathEscapeError, OSError) as exc:
            return f"ERROR: {exc}"

    def edit_file(path: str, old_str: str, new_str: str) -> str:
        """Replace exactly one occurrence of old_str with new_str in a file."""
        try:
            if not old_str:
                return "ERROR: old_str must be non-empty"
            target = resolve_in_workspace(root, path)
            if not target.is_file():
                return f"ERROR: file not found: {path}"
            text = target.read_text(encoding="utf-8")
            count = text.count(old_str)
            if count == 0:
                return "ERROR: old_str not found in file"
            if count > 1:
                return (
                    f"ERROR: old_str matched {count} times; "
                    "refuse edit (must be unique)"
                )
            target.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")
            return f"OK: edited {path}"
        except (PathEscapeError, OSError, UnicodeDecodeError) as exc:
            return f"ERROR: {exc}"

    def glob_files(pattern: str) -> str:
        """List files under the workspace matching a glob pattern (e.g. **/*.py)."""
        try:
            if not pattern:
                return "ERROR: pattern must be non-empty"
            # Disallow absolute patterns that ignore the jail.
            if pattern.startswith("/") or (len(pattern) > 1 and pattern[1] == ":"):
                return "ERROR: absolute glob patterns are not allowed"
            matches = sorted(p for p in root.glob(pattern) if p.is_file())
            if not matches:
                return "No files matched."
            rels = []
            for path in matches[:MAX_GLOB_HITS]:
                rels.append(str(path.relative_to(root)))
            suffix = ""
            if len(matches) > MAX_GLOB_HITS:
                suffix = f"\n... truncated ({len(matches)} total matches)"
            return "\n".join(rels) + suffix
        except (OSError, ValueError) as exc:
            return f"ERROR: {exc}"

    def grep_files(pattern: str, glob_pattern: str = "**/*") -> str:
        """Search file contents for a regex pattern; optional glob to limit files."""
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"ERROR: invalid regex: {exc}"
        try:
            if glob_pattern.startswith("/") or (
                len(glob_pattern) > 1 and glob_pattern[1] == ":"
            ):
                return "ERROR: absolute glob patterns are not allowed"
            hits: list[str] = []
            for path in sorted(p for p in root.glob(glob_pattern) if p.is_file()):
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        rel = path.relative_to(root)
                        hits.append(f"{rel}:{lineno}:{line}")
                        if len(hits) >= MAX_GREP_HITS:
                            hits.append("... truncated")
                            return "\n".join(hits)
            return "\n".join(hits) if hits else "No matches."
        except (OSError, ValueError) as exc:
            return f"ERROR: {exc}"

    # StructuredTool.from_function keeps explicit names/descriptions for bind_tools.
    return [
        StructuredTool.from_function(
            read_file,
            name="read_file",
            description="Read a UTF-8 text file under the workspace root.",
        ),
        StructuredTool.from_function(
            write_file,
            name="write_file",
            description="Create or overwrite a UTF-8 text file under the workspace.",
        ),
        StructuredTool.from_function(
            edit_file,
            name="edit_file",
            description=(
                "Replace exactly one unique occurrence of old_str with new_str "
                "in a workspace file."
            ),
        ),
        StructuredTool.from_function(
            glob_files,
            name="glob_files",
            description="List workspace files matching a glob pattern (e.g. **/*.py).",
        ),
        StructuredTool.from_function(
            grep_files,
            name="grep_files",
            description=(
                "Search workspace file contents with a regex; "
                "optional glob_pattern limits which files are scanned."
            ),
        ),
    ]
