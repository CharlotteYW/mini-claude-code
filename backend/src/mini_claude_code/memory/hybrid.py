"""Hybrid retrieval (M27): Elasticsearch candidates → pgvector re-rank.

Join key is ``(doc_id, chunk_index)`` — not pgvector's UUID ``id``.
ES ``_id`` is ``{doc_id}:{chunk_index}``; pgvector stores the pair as UNIQUE.
"""

from __future__ import annotations

from typing import Sequence

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.elasticsearch_chunks import (
    KeywordChunkHit,
    search_keyword,
)
from mini_claude_code.memory.pgvector_chunks import (
    MemoryChunkHit,
    search_chunks_among,
)
from mini_claude_code.memory.pgvector_notes import Embedder


def chunk_key(doc_id: str, chunk_index: int) -> tuple[str, int]:
    return (doc_id, int(chunk_index))


def keys_from_keyword_hits(
    hits: Sequence[KeywordChunkHit],
) -> list[tuple[str, int]]:
    """Stable unique ``(doc_id, chunk_index)`` in ES hit order."""
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    for h in hits:
        key = chunk_key(h.doc_id, h.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def rerank_hits_by_score(
    hits: Sequence[MemoryChunkHit],
    *,
    limit: int,
) -> list[MemoryChunkHit]:
    """Sort by score descending (None last); truncate to ``limit``."""
    limit = max(1, min(int(limit), 20))

    def sort_key(h: MemoryChunkHit) -> tuple[int, float]:
        if h.score is None:
            return (1, 0.0)
        return (0, -float(h.score))

    ordered = sorted(hits, key=sort_key)
    return list(ordered[:limit])


def search_hybrid(
    query: str,
    *,
    limit: int = 5,
    candidate_multiplier: int = 4,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> list[MemoryChunkHit]:
    """BM25 candidates from ES, then cosine re-rank among those keys in pgvector.

    Empty ES → empty list (no silent fall back to global vector search).
    """
    settings = settings or get_settings()
    q = query.strip()
    if not q:
        raise ValueError("search query must be non-empty")
    limit = max(1, min(int(limit), 20))
    mult = max(1, min(int(candidate_multiplier), 10))
    k_es = max(limit * mult, limit)
    k_es = min(k_es, 40)

    keyword_hits = search_keyword(q, limit=k_es, settings=settings)
    keys = keys_from_keyword_hits(keyword_hits)
    if not keys:
        return []

    vector_hits = search_chunks_among(
        q,
        keys,
        limit=limit,
        settings=settings,
        embedder=embedder,
    )
    return rerank_hits_by_score(vector_hits, limit=limit)
