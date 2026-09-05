"""Neo4j Document / Chunk graph (M20) — provenance + optional NEXT chain.

Complements M8 ``Fact`` nodes (crisp beliefs). Document/Chunk store *ingested
file structure*, not preferences. Simplification: no entity extraction NLP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.ingest import TextChunk
from mini_claude_code.memory.neo4j_facts import _driver


@dataclass(frozen=True)
class GraphChunkHit:
    id: str
    doc_id: str
    source_path: str
    chunk_index: int
    text: str
    title: str | None = None


def ensure_doc_constraints(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    driver = _driver(settings)
    try:
        with driver.session() as session:
            session.run(
                "CREATE CONSTRAINT document_id IF NOT EXISTS "
                "FOR (d:Document) REQUIRE d.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
                "FOR (c:Chunk) REQUIRE c.id IS UNIQUE"
            )
    finally:
        driver.close()


def delete_document_graph(
    doc_id: str, *, settings: Settings | None = None
) -> None:
    settings = settings or get_settings()
    driver = _driver(settings)
    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (d:Document {id: $doc_id})
                OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
                DETACH DELETE c, d
                """,
                doc_id=doc_id,
            )
    finally:
        driver.close()


def write_document_chunks(
    chunks: Sequence[TextChunk],
    *,
    settings: Settings | None = None,
    replace: bool = True,
) -> int:
    """Write Document + Chunk nodes and HAS_CHUNK / NEXT edges."""
    if not chunks:
        return 0
    settings = settings or get_settings()
    ensure_doc_constraints(settings)

    # Group by doc_id (ingest usually one file at a time, but be safe).
    by_doc: dict[str, list[TextChunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)

    driver = _driver(settings)
    written = 0
    try:
        with driver.session() as session:
            for doc_id, group in by_doc.items():
                group = sorted(group, key=lambda x: x.chunk_index)
                if replace:
                    session.run(
                        """
                        MATCH (d:Document {id: $doc_id})
                        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
                        DETACH DELETE c, d
                        """,
                        doc_id=doc_id,
                    )
                title = group[0].title
                source_path = group[0].source_path
                session.run(
                    """
                    CREATE (d:Document {
                      id: $doc_id,
                      source_path: $source_path,
                      title: $title,
                      created_at: datetime()
                    })
                    """,
                    doc_id=doc_id,
                    source_path=source_path,
                    title=title,
                )
                prev_id: str | None = None
                for c in group:
                    chunk_id = f"{c.doc_id}:{c.chunk_index}"
                    session.run(
                        """
                        MATCH (d:Document {id: $doc_id})
                        CREATE (c:Chunk {
                          id: $chunk_id,
                          doc_id: $doc_id,
                          source_path: $source_path,
                          chunk_index: $chunk_index,
                          text: $text,
                          title: $title,
                          created_at: datetime()
                        })
                        CREATE (d)-[:HAS_CHUNK]->(c)
                        """,
                        doc_id=c.doc_id,
                        chunk_id=chunk_id,
                        source_path=c.source_path,
                        chunk_index=c.chunk_index,
                        text=c.text,
                        title=c.title,
                    )
                    if prev_id is not None:
                        session.run(
                            """
                            MATCH (a:Chunk {id: $prev})
                            MATCH (b:Chunk {id: $curr})
                            CREATE (a)-[:NEXT]->(b)
                            """,
                            prev=prev_id,
                            curr=chunk_id,
                        )
                    prev_id = chunk_id
                    written += 1
    finally:
        driver.close()
    return written


def search_chunks_keyword(
    query: str,
    *,
    limit: int = 5,
    settings: Settings | None = None,
) -> list[GraphChunkHit]:
    """Case-insensitive CONTAINS on Chunk.text (keyword, not semantic)."""
    settings = settings or get_settings()
    q = query.strip()
    if not q:
        raise ValueError("search query must be non-empty")
    limit = max(1, min(int(limit), 20))

    driver = _driver(settings)
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (c:Chunk)
                WHERE toLower(c.text) CONTAINS toLower($q)
                   OR toLower(coalesce(c.title, '')) CONTAINS toLower($q)
                   OR toLower(c.source_path) CONTAINS toLower($q)
                RETURN c.id AS id, c.doc_id AS doc_id,
                       c.source_path AS source_path,
                       c.chunk_index AS chunk_index,
                       c.text AS text, c.title AS title
                ORDER BY c.chunk_index ASC
                LIMIT $limit
                """,
                q=q,
                limit=limit,
            )
            return [
                GraphChunkHit(
                    id=str(r["id"]),
                    doc_id=str(r["doc_id"]),
                    source_path=str(r["source_path"]),
                    chunk_index=int(r["chunk_index"]),
                    text=str(r["text"]),
                    title=str(r["title"]) if r["title"] is not None else None,
                )
                for r in result
            ]
    finally:
        driver.close()
