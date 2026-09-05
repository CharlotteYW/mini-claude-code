"""Document ingestion helpers (M20) — clean + chunk + metadata.

Neo4j / pgvector only *store* what this pipeline produces. Chunking is not a
database feature; it is an ingestion concern (teaching contrast with M8
one-shot remember_* tools).

Simplification: character size + overlap splitter. Production often uses
token-aware or structure-aware (markdown heading / AST) chunkers.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# Default teaching sizes (chars ≈ rough token budget for small models).
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120

_SUPPORTED_SUFFIXES = frozenset({".md", ".txt", ".markdown"})


@dataclass(frozen=True)
class TextChunk:
    """One chunk ready for embed/write."""

    doc_id: str
    source_path: str
    chunk_index: int
    text: str
    title: str | None = None


def doc_id_for_path(source_path: str) -> str:
    """Stable id from normalized path (re-ingest replaces by doc_id)."""
    normalized = source_path.replace("\\", "/").strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"doc-{digest}"


def clean_text(raw: str) -> str:
    """Normalize newlines and collapse excessive blank lines; strip ends."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_title(cleaned: str, *, fallback: str | None = None) -> str | None:
    """First markdown H1, else first non-empty line, else fallback."""
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
        return stripped[:120] if stripped else fallback
    return fallback


def chunk_text(
    text: str,
    *,
    doc_id: str,
    source_path: str,
    title: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Split cleaned text into overlapping chunks with monotonic indexes."""
    cleaned = clean_text(text)
    if not cleaned:
        return []

    size = max(1, int(chunk_size))
    overlap = max(0, min(int(chunk_overlap), size - 1))
    title = title if title is not None else extract_title(cleaned)

    if len(cleaned) <= size:
        return [
            TextChunk(
                doc_id=doc_id,
                source_path=source_path,
                chunk_index=0,
                text=cleaned,
                title=title,
            )
        ]

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(cleaned):
        end = min(start + size, len(cleaned))
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(
                TextChunk(
                    doc_id=doc_id,
                    source_path=source_path,
                    chunk_index=index,
                    text=piece,
                    title=title,
                )
            )
            index += 1
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
        if start >= end:
            # Guard pathological overlap == size after max() clamps.
            start = end
    return chunks


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def is_ingestible_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES


def resolve_ingest_paths(root: Path, pattern_or_path: str) -> list[Path]:
    """Resolve a file, directory, or glob under ``root`` (already jailed).

    ``pattern_or_path`` is relative to ``root`` or an absolute path already
    verified to lie under ``root``.
    """
    root = root.expanduser().resolve()
    raw = Path(pattern_or_path)
    candidate = (raw if raw.is_absolute() else (root / raw)).resolve()

    if any(ch in pattern_or_path for ch in "*?["):
        # Glob relative to root.
        matches = sorted(p for p in root.glob(pattern_or_path) if is_ingestible_file(p))
        return matches

    if candidate.is_file():
        if not is_ingestible_file(candidate):
            raise ValueError(
                f"unsupported file type {candidate.suffix!r} "
                f"(supported: {sorted(_SUPPORTED_SUFFIXES)})"
            )
        return [candidate]

    if candidate.is_dir():
        found: list[Path] = []
        for p in sorted(candidate.rglob("*")):
            if is_ingestible_file(p):
                found.append(p)
        return found

    raise FileNotFoundError(f"no file or directory at {pattern_or_path!r}")


def chunks_from_file(
    path: Path,
    *,
    workspace_root: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Load one file and produce chunks with workspace-relative source_path."""
    root = workspace_root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    rel = str(resolved.relative_to(root)).replace("\\", "/")
    doc_id = doc_id_for_path(rel)
    body = load_text_file(resolved)
    return chunk_text(
        body,
        doc_id=doc_id,
        source_path=rel,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
