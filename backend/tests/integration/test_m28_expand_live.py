"""M28 integration: NEXT expand after Neo4j Document/Chunk write."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.expand import expand_chunks
from mini_claude_code.memory.ingest import TextChunk
from mini_claude_code.memory.neo4j_docs import delete_document_graph, write_document_chunks

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _neo4j_or_skip(settings: Settings) -> None:
    neo4j = pytest.importorskip("neo4j")
    try:
        driver = neo4j.GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j unavailable: {exc}")


def test_expand_chunks_middle_and_edge(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _neo4j_or_skip(settings)

    doc_id = f"m28-{uuid4().hex[:10]}"
    source = f"docs/{doc_id}.md"
    chunks = [
        TextChunk(doc_id, source, 0, "CHUNK-ZERO preface"),
        TextChunk(doc_id, source, 1, "CHUNK-ONE island hit"),
        TextChunk(doc_id, source, 2, "CHUNK-TWO aftermath"),
        TextChunk(doc_id, source, 3, "CHUNK-THREE tail"),
    ]
    try:
        written = write_document_chunks(chunks, settings=settings, replace=True)
        assert written == 4

        mid = expand_chunks(
            doc_id=doc_id, chunk_index=1, radius=1, settings=settings
        )
        assert [h.chunk_index for h in mid] == [0, 1, 2]
        assert all(h.source_path == source for h in mid)
        assert "CHUNK-ZERO" in mid[0].text
        assert "CHUNK-ONE" in mid[1].text
        assert "CHUNK-TWO" in mid[2].text

        by_id = expand_chunks(chunk_id=f"{doc_id}:1", radius=1, settings=settings)
        assert [h.chunk_index for h in by_id] == [0, 1, 2]

        edge = expand_chunks(
            doc_id=doc_id, chunk_index=0, radius=1, settings=settings
        )
        assert [h.chunk_index for h in edge] == [0, 1]
        assert all(h.chunk_index >= 0 for h in edge)

        missing = expand_chunks(
            doc_id=doc_id, chunk_index=99, radius=1, settings=settings
        )
        assert missing == []
    finally:
        delete_document_graph(doc_id, settings=settings)
