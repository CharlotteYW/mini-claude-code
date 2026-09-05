"""M20 integration: ingest → pgvector / Neo4j (skip if services unavailable)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.neo4j_docs import search_chunks_keyword
from mini_claude_code.memory.pgvector_chunks import search_chunks
from mini_claude_code.memory.pipeline import ingest_paths

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _postgres_or_skip(settings: Settings) -> None:
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")


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


def _embedder_or_skip(settings: Settings):
    try:
        from mini_claude_code.memory.pgvector_notes import create_ollama_embedder

        emb = create_ollama_embedder(settings)
        vec = emb.embed_query("ping")
        if len(vec) != settings.embedding_dimensions:
            pytest.skip(
                f"embed dim mismatch {len(vec)} vs {settings.embedding_dimensions}"
            )
        return emb
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Ollama embedder unavailable: {exc}")


def test_ingest_pgvector_and_search(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    embedder = _embedder_or_skip(settings)

    token = f"m20-pg-{uuid4().hex[:8]}"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        f"# Guide\n\nThe secret codeword is {token} for retrieval.\n",
        encoding="utf-8",
    )

    result = ingest_paths(
        "docs",
        workspace_root=tmp_path,
        settings=settings,
        embedder=embedder,
        write_pgvector=True,
        write_neo4j=False,
    )
    assert not result.errors, result.errors
    assert result.pgvector_written >= 1

    hits = search_chunks(
        f"secret codeword {token}",
        limit=3,
        settings=settings,
        embedder=embedder,
    )
    assert any(token in h.text and "docs/guide.md" in h.source_path for h in hits)


def test_ingest_neo4j_document_chunks(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _neo4j_or_skip(settings)

    token = f"m20-neo-{uuid4().hex[:8]}"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "facts.md").write_text(
        f"# Facts\n\nNeo4j stores the marker {token} after ingest.\n",
        encoding="utf-8",
    )

    result = ingest_paths(
        "docs/facts.md",
        workspace_root=tmp_path,
        settings=settings,
        write_pgvector=False,
        write_neo4j=True,
    )
    assert not result.errors, result.errors
    assert result.neo4j_written >= 1

    hits = search_chunks_keyword(token, limit=5, settings=settings)
    assert any(token in h.text and h.source_path.endswith("facts.md") for h in hits)


def test_ingest_dual_write_when_available(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    _neo4j_or_skip(settings)
    embedder = _embedder_or_skip(settings)

    token = f"m20-dual-{uuid4().hex[:8]}"
    (tmp_path / "note.md").write_text(
        f"# Dual\n\nDual-write marker {token}.\n",
        encoding="utf-8",
    )
    result = ingest_paths(
        "note.md",
        workspace_root=tmp_path,
        settings=settings,
        embedder=embedder,
        write_pgvector=True,
        write_neo4j=True,
    )
    assert not result.errors, result.errors
    assert result.pgvector_written >= 1
    assert result.neo4j_written >= 1
