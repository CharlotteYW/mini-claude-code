"""Graph-neighbor expand (M28): ordered window around a chunk hit.

Join / cite key stays ``(doc_id, chunk_index)`` / ``{doc_id}:{chunk_index}``.
Neo4j walk uses ``NEXT`` (ingest already writes the chain); index math is the
pure teaching helper for radius/bounds.
"""

from __future__ import annotations

from typing import Sequence

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.neo4j_docs import GraphChunkHit, expand_chunks_via_next


def clamp_radius(radius: int, *, default: int = 1, lo: int = 1, hi: int = 3) -> int:
    """Default radius 1; clamp to ``[lo, hi]`` (Plan: avoid context bloat)."""
    try:
        r = int(radius)
    except (TypeError, ValueError):
        return default
    if r < lo:
        return lo
    if r > hi:
        return hi
    return r


def expand_index_window(
    center: int,
    radius: int,
    *,
    min_index: int = 0,
    max_index: int | None = None,
) -> list[int]:
    """Pure ±N index list inclusive of center, clipped to ``[min_index, max_index]``."""
    center = int(center)
    radius = clamp_radius(radius)
    lo = max(int(min_index), center - radius)
    hi = center + radius
    if max_index is not None:
        hi = min(int(max_index), hi)
    if hi < lo:
        return []
    return list(range(lo, hi + 1))


def parse_chunk_ref(
    *,
    doc_id: str | None = None,
    chunk_index: int | None = None,
    chunk_id: str | None = None,
) -> tuple[str, int]:
    """Resolve ``(doc_id, chunk_index)`` from pair or ``{doc_id}:{chunk_index}``."""
    if chunk_id is not None and str(chunk_id).strip():
        raw = str(chunk_id).strip()
        if ":" not in raw:
            raise ValueError(
                "chunk_id must look like '{doc_id}:{chunk_index}' "
                f"(got {raw!r})"
            )
        doc_part, idx_part = raw.rsplit(":", 1)
        if not doc_part:
            raise ValueError("chunk_id missing doc_id before ':'")
        try:
            idx = int(idx_part)
        except ValueError as exc:
            raise ValueError(
                f"chunk_id index must be int after ':' (got {idx_part!r})"
            ) from exc
        return doc_part, idx

    if doc_id is None or str(doc_id).strip() == "":
        raise ValueError("doc_id is required when chunk_id is omitted")
    if chunk_index is None:
        raise ValueError("chunk_index is required when chunk_id is omitted")
    return str(doc_id).strip(), int(chunk_index)


def format_chunk_citation(hit: GraphChunkHit) -> str:
    """Stable cite used in tool output: ``source_path#chunk_index``."""
    return f"{hit.source_path}#{hit.chunk_index}"


def format_expand_hits(hits: Sequence[GraphChunkHit]) -> str:
    if not hits:
        return "No chunks in expand window."
    lines: list[str] = []
    for h in hits:
        title = f" title={h.title!r}" if h.title else ""
        lines.append(f"- [{format_chunk_citation(h)}{title}] {h.text}")
    return "\n".join(lines)


def expand_chunks(
    *,
    doc_id: str | None = None,
    chunk_index: int | None = None,
    chunk_id: str | None = None,
    radius: int = 1,
    settings: Settings | None = None,
) -> list[GraphChunkHit]:
    """Return ordered ±radius neighbors (incl. center) via Neo4j ``NEXT``.

    Empty list if the center chunk is missing. Does not call search tools.
    """
    settings = settings or get_settings()
    doc, idx = parse_chunk_ref(
        doc_id=doc_id, chunk_index=chunk_index, chunk_id=chunk_id
    )
    radius = clamp_radius(radius)
    return expand_chunks_via_next(
        doc_id=doc, chunk_index=idx, radius=radius, settings=settings
    )
