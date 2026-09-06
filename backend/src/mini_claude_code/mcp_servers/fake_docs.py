"""Fake docs MCP server (M26) — teaching content policy.

Tools:
  - list_docs() → doc ids + titles
  - read_doc(doc_id) → body, or CONTENT_POLICY_DENIED when markers present

**Server-enforced:** ``read_doc`` refuses before returning the body (even if the
client forgets to wrap). Pair with ``mini_claude_code.content_policy`` client wrap.

Run: ``python -m mini_claude_code.mcp_servers.fake_docs`` (stdio).
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mini_claude_code.content_policy import (
    content_policy_denial,
    find_policy_marker,
    markdown_h1_title,
)

mcp = FastMCP("fake-docs")

_DATA_DIR = Path(__file__).resolve().parent / "fake_docs_data"


def _docs() -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not _DATA_DIR.is_dir():
        return out
    for path in sorted(_DATA_DIR.glob("*.md")):
        out[path.stem] = path
    return out


def _title_for(path: Path, text: str) -> str:
    h1 = markdown_h1_title(text)
    if h1:
        return h1
    return path.stem


@mcp.tool()
def list_docs() -> str:
    """List available teaching documents (id + title). Does not return bodies."""
    rows: list[str] = []
    for doc_id, path in _docs().items():
        text = path.read_text(encoding="utf-8")
        title = _title_for(path, text)
        marker = find_policy_marker(text, title=title)
        flag = f" [restricted:{marker}]" if marker else ""
        rows.append(f"- {doc_id}: {title}{flag}")
    if not rows:
        return "No documents in fake_docs_data/."
    return "Documents:\n" + "\n".join(rows)


@mcp.tool()
def read_doc(doc_id: str) -> str:
    """Read a document by id. Refuses bodies marked no-ai / CONFIDENTIAL (server-side)."""
    docs = _docs()
    key = doc_id.strip()
    if key not in docs:
        known = ", ".join(sorted(docs)) or "(none)"
        return f"ERROR: unknown doc_id={doc_id!r}; known: {known}"
    path = docs[key]
    text = path.read_text(encoding="utf-8")
    title = _title_for(path, text)
    matched = find_policy_marker(text, title=title)
    if matched is not None:
        # Server-enforced: never return SECRET_BODY_* lines.
        return content_policy_denial(matched, source=f"fake_docs_server:{key}")
    return text


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
