"""M21 integration: Elasticsearch index + search (skip if ES down)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.elasticsearch_chunks import search_keyword, write_chunks_es
from mini_claude_code.memory.ingest import TextChunk
from mini_claude_code.memory.pipeline import ingest_paths

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _es_or_skip(settings: Settings) -> None:
    pytest.importorskip("elasticsearch")
    try:
        from elasticsearch import Elasticsearch

        client = Elasticsearch(settings.elasticsearch_url)
        if not client.ping():
            pytest.skip(f"Elasticsearch not pingable at {settings.elasticsearch_url}")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Elasticsearch unavailable: {exc}")


def test_index_and_search_keyword_roundtrip() -> None:
    settings = _load_repo_settings()
    _es_or_skip(settings)
    token = f"M21_TOKEN_{uuid4().hex[:8]}"
    chunk = TextChunk(
        doc_id=f"doc-m21-{uuid4().hex[:8]}",
        source_path="docs/m21-live.md",
        chunk_index=0,
        text=f"Integration fixture contains {token} for BM25.",
        title="M21 live",
    )
    written = write_chunks_es([chunk], settings=settings, replace=True)
    assert written >= 1
    hits = search_keyword(token, limit=5, settings=settings)
    assert any(token in h.text and h.source_path.endswith("m21-live.md") for h in hits)


def test_ingest_paths_writes_elasticsearch(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _es_or_skip(settings)
    token = f"M21_INGEST_{uuid4().hex[:8]}"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.md").write_text(
        f"# Note\n\nExact marker {token} should rank via BM25.\n",
        encoding="utf-8",
    )
    result = ingest_paths(
        "docs",
        workspace_root=tmp_path,
        settings=settings,
        write_pgvector=False,
        write_neo4j=False,
        write_elasticsearch=True,
    )
    assert not result.errors, result.errors
    assert result.elasticsearch_written >= 1
    hits = search_keyword(token, limit=3, settings=settings)
    assert any(token in h.text for h in hits)
