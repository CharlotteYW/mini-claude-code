"""Store-agnostic ingest orchestration (M20).

Pipeline: resolve paths → chunk → write pgvector and/or Neo4j.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.ingest import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    TextChunk,
    chunks_from_file,
    resolve_ingest_paths,
)
from mini_claude_code.memory.neo4j_docs import write_document_chunks
from mini_claude_code.memory.pgvector_chunks import write_chunks
from mini_claude_code.memory.pgvector_notes import Embedder


@dataclass
class IngestResult:
    files: list[str] = field(default_factory=list)
    chunks: list[TextChunk] = field(default_factory=list)
    pgvector_written: int = 0
    neo4j_written: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"ingested files={len(self.files)} chunks={len(self.chunks)} "
            f"pgvector={self.pgvector_written} neo4j={self.neo4j_written}"
        ]
        for p in self.files:
            n = sum(1 for c in self.chunks if c.source_path == p)
            lines.append(f"  - {p} ({n} chunks)")
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        return "\n".join(lines)


def _resolve_under_root(root: Path, user_path: str) -> Path:
    """Same semantics as path_jail.resolve_in_workspace (avoid tools import cycle)."""
    raw = Path(user_path).expanduser()
    candidate = (raw if raw.is_absolute() else (root / raw)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"path escapes workspace root ({root}): {user_path!r}"
        ) from exc
    return candidate


def ingest_paths(
    pattern_or_path: str,
    *,
    workspace_root: Path,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    write_pgvector: bool = True,
    write_neo4j: bool = True,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestResult:
    """Jail-resolve ``pattern_or_path``, chunk files, dual-write stores."""
    settings = settings or get_settings()
    root = workspace_root.expanduser().resolve()
    result = IngestResult()

    try:
        if any(ch in pattern_or_path for ch in "*?["):
            probe = pattern_or_path.split("*", 1)[0].split("?", 1)[0]
            if probe and ".." in Path(probe).parts:
                raise ValueError(
                    f"path escapes workspace root ({root}): {pattern_or_path!r}"
                )
            paths = resolve_ingest_paths(root, pattern_or_path)
        else:
            target = _resolve_under_root(root, pattern_or_path)
            paths = resolve_ingest_paths(root, str(target.relative_to(root)))
    except (FileNotFoundError, ValueError, OSError) as exc:
        result.errors.append(str(exc))
        return result

    if not paths:
        result.errors.append(f"no ingestible .md/.txt files under {pattern_or_path!r}")
        return result

    all_chunks: list[TextChunk] = []
    for path in paths:
        try:
            chunks = chunks_from_file(
                path,
                workspace_root=root,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{path}: {exc}")
            continue
        if not chunks:
            result.errors.append(f"{path}: empty after clean")
            continue
        rel = chunks[0].source_path
        result.files.append(rel)
        all_chunks.extend(chunks)

    result.chunks = all_chunks
    if not all_chunks:
        return result

    if write_pgvector:
        try:
            result.pgvector_written = write_chunks(
                all_chunks, settings=settings, embedder=embedder, replace=True
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"pgvector: {exc}")

    if write_neo4j:
        try:
            result.neo4j_written = write_document_chunks(
                all_chunks, settings=settings, replace=True
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"neo4j: {exc}")

    return result
