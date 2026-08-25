"""Minimal pgvector note memory (M8 option B).

Semantic / fuzzy recall — not a second chat log (checkpointer) and not
structured Neo4j facts. Simplification: one table, cosine distance, fixed
embedding dimension for the configured model (default nomic-embed-text @ 768).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from mini_claude_code.config import Settings, get_settings

EmbedFn = Callable[[str], list[float]]


class Embedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class MemoryNote:
    id: str
    text: str
    score: float | None = None


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  text text NOT NULL,
  embedding vector({dim}) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in values) + "]"


def ensure_notes_schema(
    settings: Settings | None = None, *, dim: int | None = None
) -> None:
    settings = settings or get_settings()
    dim = dim or settings.embedding_dimensions
    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(_SCHEMA_SQL.format(dim=int(dim)))
        conn.commit()


def create_ollama_embedder(settings: Settings | None = None) -> Embedder:
    from langchain_ollama import OllamaEmbeddings

    settings = settings or get_settings()
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
    )


def remember_note(
    text: str,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> MemoryNote:
    settings = settings or get_settings()
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("note text must be non-empty")

    embedder = embedder or create_ollama_embedder(settings)
    vector = embedder.embed_query(cleaned)
    if len(vector) != settings.embedding_dimensions:
        raise ValueError(
            f"embedding dim {len(vector)} != EMBEDDING_DIMENSIONS "
            f"{settings.embedding_dimensions} (model={settings.embedding_model})"
        )

    ensure_notes_schema(settings, dim=settings.embedding_dimensions)
    import psycopg

    lit = _vector_literal(vector)
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memory_notes (text, embedding)
                VALUES (%s, %s::vector)
                RETURNING id::text
                """,
                (cleaned, lit),
            )
            row = cur.fetchone()
        conn.commit()
    assert row is not None
    return MemoryNote(id=str(row[0]), text=cleaned)


def recall_notes(
    query: str,
    *,
    limit: int = 5,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> list[MemoryNote]:
    settings = settings or get_settings()
    q = query.strip()
    if not q:
        raise ValueError("recall query must be non-empty")
    limit = max(1, min(int(limit), 20))

    embedder = embedder or create_ollama_embedder(settings)
    vector = embedder.embed_query(q)
    if len(vector) != settings.embedding_dimensions:
        raise ValueError(
            f"embedding dim {len(vector)} != EMBEDDING_DIMENSIONS "
            f"{settings.embedding_dimensions}"
        )

    ensure_notes_schema(settings, dim=settings.embedding_dimensions)
    import psycopg

    lit = _vector_literal(vector)
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, text,
                       (1 - (embedding <=> %s::vector))::float8 AS score
                FROM memory_notes
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (lit, lit, limit),
            )
            rows = cur.fetchall()
    return [
        MemoryNote(id=str(r[0]), text=str(r[1]), score=float(r[2])) for r in rows
    ]
