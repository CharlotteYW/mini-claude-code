"""Elasticsearch chunk index (M21) — BM25 / full-text over ingested docs.

Complements M20 pgvector (semantic) and Neo4j (structure). We call ES's
inverted-index + BM25 via the search API; we do not reimplement BM25.
Simplification: single index, no auth, sync index on ingest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.ingest import TextChunk

DEFAULT_INDEX = "mcc_chunks"

# Stable mapping for unit tests + ensure_index (engine applies BM25 on text fields).
CHUNK_INDEX_MAPPINGS: dict[str, Any] = {
    "properties": {
        "doc_id": {"type": "keyword"},
        "source_path": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "title": {
            "type": "text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        },
        "text": {"type": "text"},
    }
}


@dataclass(frozen=True)
class KeywordChunkHit:
    id: str
    doc_id: str
    source_path: str
    chunk_index: int
    text: str
    title: str | None = None
    score: float | None = None


def chunk_to_es_document(chunk: TextChunk) -> dict[str, Any]:
    """Serialize a TextChunk to an Elasticsearch document body (no network)."""
    return {
        "doc_id": chunk.doc_id,
        "source_path": chunk.source_path,
        "chunk_index": chunk.chunk_index,
        "title": chunk.title,
        "text": chunk.text,
    }


def chunk_document_id(chunk: TextChunk) -> str:
    return f"{chunk.doc_id}:{chunk.chunk_index}"


def build_keyword_query(query: str) -> dict[str, Any]:
    """multi_match query clause — title boosted over body text."""
    return {
        "multi_match": {
            "query": query,
            "fields": ["title^2", "text", "source_path"],
            "type": "best_fields",
        }
    }


def _client(settings: Settings):
    from elasticsearch import Elasticsearch

    return Elasticsearch(settings.elasticsearch_url)


def ensure_index(
    settings: Settings | None = None, *, index: str | None = None
) -> str:
    settings = settings or get_settings()
    index = index or settings.elasticsearch_index
    client = _client(settings)
    if not client.indices.exists(index=index):
        client.indices.create(index=index, mappings=CHUNK_INDEX_MAPPINGS)
    return index


def delete_chunks_for_doc(
    doc_id: str,
    *,
    settings: Settings | None = None,
    index: str | None = None,
) -> int:
    settings = settings or get_settings()
    index = ensure_index(settings, index=index)
    client = _client(settings)
    resp = client.delete_by_query(
        index=index,
        query={"term": {"doc_id": doc_id}},
        refresh=True,
        conflicts="proceed",
    )
    return int(resp.get("deleted", 0))


def write_chunks_es(
    chunks: Sequence[TextChunk],
    *,
    settings: Settings | None = None,
    replace: bool = True,
    index: str | None = None,
) -> int:
    """Index chunks into Elasticsearch. Replaces prior docs for each doc_id."""
    if not chunks:
        return 0
    settings = settings or get_settings()
    index = ensure_index(settings, index=index)
    client = _client(settings)

    if replace:
        seen: set[str] = set()
        for c in chunks:
            if c.doc_id not in seen:
                delete_chunks_for_doc(c.doc_id, settings=settings, index=index)
                seen.add(c.doc_id)

    try:
        from elasticsearch.helpers import bulk

        actions = [
            {
                "_index": index,
                "_id": chunk_document_id(c),
                "_source": chunk_to_es_document(c),
            }
            for c in chunks
        ]
        success, _errors = bulk(client, actions, refresh=True)
        return int(success)
    except Exception:
        written = 0
        for c in chunks:
            client.index(
                index=index,
                id=chunk_document_id(c),
                document=chunk_to_es_document(c),
                refresh=True,
            )
            written += 1
        return written


def search_keyword(
    query: str,
    *,
    limit: int = 5,
    settings: Settings | None = None,
    index: str | None = None,
) -> list[KeywordChunkHit]:
    settings = settings or get_settings()
    q = query.strip()
    if not q:
        raise ValueError("search query must be non-empty")
    limit = max(1, min(int(limit), 20))
    index = ensure_index(settings, index=index)
    client = _client(settings)
    resp = client.search(
        index=index,
        size=limit,
        query=build_keyword_query(q),
    )
    hits: list[KeywordChunkHit] = []
    for h in resp.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        hits.append(
            KeywordChunkHit(
                id=str(h.get("_id", "")),
                doc_id=str(src.get("doc_id", "")),
                source_path=str(src.get("source_path", "")),
                chunk_index=int(src.get("chunk_index", 0)),
                text=str(src.get("text", "")),
                title=str(src["title"]) if src.get("title") is not None else None,
                score=float(h["_score"]) if h.get("_score") is not None else None,
            )
        )
    return hits
