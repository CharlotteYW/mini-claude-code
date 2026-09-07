"""pgvector document chunks (M20) — semantic search with provenance.

Extends M8's thin ``memory_notes`` with doc_id / source_path / chunk_index.
Ad-hoc ``remember_note`` remains for one-off blurbs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.ingest import TextChunk
from mini_claude_code.memory.pgvector_notes import Embedder, _vector_literal, create_ollama_embedder

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id text NOT NULL,
  source_path text NOT NULL,
  chunk_index int NOT NULL,
  title text,
  text text NOT NULL,
  embedding vector({dim}) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS memory_chunks_doc_id_idx ON memory_chunks (doc_id);
"""


@dataclass(frozen=True)
class MemoryChunkHit:
    id: str
    doc_id: str
    source_path: str
    chunk_index: int
    text: str
    title: str | None = None
    score: float | None = None


def ensure_chunks_schema(
    settings: Settings | None = None, *, dim: int | None = None
) -> None:
    settings = settings or get_settings()
    dim = dim or settings.embedding_dimensions
    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            for stmt in _SCHEMA_SQL.format(dim=int(dim)).split(";"):
                s = stmt.strip()
                if s:
                    cur.execute(s)
        conn.commit()


def delete_chunks_for_doc(
    doc_id: str, *, settings: Settings | None = None
) -> int:
    settings = settings or get_settings()
    ensure_chunks_schema(settings)
    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM memory_chunks WHERE doc_id = %s",
                (doc_id,),
            )
            deleted = cur.rowcount
        conn.commit()
    return int(deleted)


def write_chunks(
    chunks: Sequence[TextChunk],
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    replace: bool = True,
) -> int:
    """Embed and insert chunks. If ``replace``, delete prior rows for each doc_id."""
    if not chunks:
        return 0
    settings = settings or get_settings()
    embedder = embedder or create_ollama_embedder(settings)
    ensure_chunks_schema(settings, dim=settings.embedding_dimensions)

    if replace:
        seen: set[str] = set()
        for c in chunks:
            if c.doc_id not in seen:
                delete_chunks_for_doc(c.doc_id, settings=settings)
                seen.add(c.doc_id)

    import psycopg

    written = 0
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            for c in chunks:
                vector = embedder.embed_query(c.text)
                if len(vector) != settings.embedding_dimensions:
                    raise ValueError(
                        f"embedding dim {len(vector)} != EMBEDDING_DIMENSIONS "
                        f"{settings.embedding_dimensions}"
                    )
                lit = _vector_literal(vector)
                cur.execute(
                    """
                    INSERT INTO memory_chunks
                      (doc_id, source_path, chunk_index, title, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s::vector)
                    """,
                    (
                        c.doc_id,
                        c.source_path,
                        c.chunk_index,
                        c.title,
                        c.text,
                        lit,
                    ),
                )
                written += 1
        conn.commit()
    return written


def search_chunks(
    query: str,
    *,
    limit: int = 5,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> list[MemoryChunkHit]:
    settings = settings or get_settings()
    q = query.strip()
    if not q:
        raise ValueError("search query must be non-empty")
    limit = max(1, min(int(limit), 20))

    embedder = embedder or create_ollama_embedder(settings)
    vector = embedder.embed_query(q)
    if len(vector) != settings.embedding_dimensions:
        raise ValueError(
            f"embedding dim {len(vector)} != EMBEDDING_DIMENSIONS "
            f"{settings.embedding_dimensions}"
        )

    ensure_chunks_schema(settings, dim=settings.embedding_dimensions)
    import psycopg

    lit = _vector_literal(vector)
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, doc_id, source_path, chunk_index, title, text,
                       (1 - (embedding <=> %s::vector))::float8 AS score
                FROM memory_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (lit, lit, limit),
            )
            rows = cur.fetchall()
    return [
        MemoryChunkHit(
            id=str(r[0]),
            doc_id=str(r[1]),
            source_path=str(r[2]),
            chunk_index=int(r[3]),
            title=str(r[4]) if r[4] is not None else None,
            text=str(r[5]),
            score=float(r[6]),
        )
        for r in rows
    ]


def search_chunks_among(
    query: str,
    keys: Sequence[tuple[str, int]],
    *,
    limit: int = 5,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> list[MemoryChunkHit]:
    """Cosine search restricted to ``(doc_id, chunk_index)`` candidates (M27)."""
    settings = settings or get_settings()
    q = query.strip()
    if not q:
        raise ValueError("search query must be non-empty")
    if not keys:
        return []
    limit = max(1, min(int(limit), 20))

    # Dedupe while preserving order.
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int]] = []
    for doc_id, chunk_index in keys:
        key = (str(doc_id), int(chunk_index))
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)

    embedder = embedder or create_ollama_embedder(settings)
    vector = embedder.embed_query(q)
    if len(vector) != settings.embedding_dimensions:
        raise ValueError(
            f"embedding dim {len(vector)} != EMBEDDING_DIMENSIONS "
            f"{settings.embedding_dimensions}"
        )

    ensure_chunks_schema(settings, dim=settings.embedding_dimensions)
    import psycopg

    lit = _vector_literal(vector)
    # VALUES list for (doc_id, chunk_index) pairs.
    values_sql = ",".join(["(%s,%s)"] * len(unique))
    params: list[object] = [lit]
    for doc_id, chunk_index in unique:
        params.extend([doc_id, chunk_index])
    params.extend([lit, limit])

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.id::text, c.doc_id, c.source_path, c.chunk_index, c.title,
                       c.text,
                       (1 - (c.embedding <=> %s::vector))::float8 AS score
                FROM memory_chunks c
                INNER JOIN (VALUES {values_sql}) AS k(doc_id, chunk_index)
                  ON c.doc_id = k.doc_id AND c.chunk_index = k.chunk_index::int
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    return [
        MemoryChunkHit(
            id=str(r[0]),
            doc_id=str(r[1]),
            source_path=str(r[2]),
            chunk_index=int(r[3]),
            title=str(r[4]) if r[4] is not None else None,
            text=str(r[5]),
            score=float(r[6]),
        )
        for r in rows
    ]
