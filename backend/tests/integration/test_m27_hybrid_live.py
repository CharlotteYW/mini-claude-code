"""M27 integration: hybrid ES → pgvector (skip if ES/Postgres down)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.hybrid import search_hybrid
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


def _es_or_skip(settings: Settings) -> None:
    pytest.importorskip("elasticsearch")
    try:
        from elasticsearch import Elasticsearch

        client = Elasticsearch(settings.elasticsearch_url)
        if not client.ping():
            pytest.skip(f"Elasticsearch not pingable at {settings.elasticsearch_url}")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Elasticsearch unavailable: {exc}")


def _bias_embedder(dim: int):
    """Axis-0 = preferred semantic; axis-1 = distractor (no Ollama required)."""

    class _Bias:
        def embed_query(self, text: str) -> list[float]:
            vec = [0.0] * dim
            lower = text.lower()
            if "preferred_semantic" in lower or "preferred topic" in lower:
                vec[0] = 1.0
            else:
                vec[1] = 1.0
            return vec

    return _Bias()


def test_hybrid_reranks_keyword_candidates(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    _es_or_skip(settings)
    emb = _bias_embedder(settings.embedding_dimensions)

    token = f"M27_TOKEN_{uuid4().hex[:8]}"
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "preferred.md").write_text(
        f"# Preferred\n\n{token} PREFERRED_SEMANTIC launch revenue narrative.\n",
        encoding="utf-8",
    )
    (docs / "distractor.md").write_text(
        f"# Distractor\n\n{token} kitchen recipes and pasta water tips.\n",
        encoding="utf-8",
    )

    result = ingest_paths(
        "docs",
        workspace_root=tmp_path,
        settings=settings,
        embedder=emb,
        write_pgvector=True,
        write_neo4j=False,
        write_elasticsearch=True,
    )
    assert not result.errors, result.errors
    assert result.pgvector_written >= 2
    assert result.elasticsearch_written >= 2

    hits = search_hybrid(
        f"{token} preferred topic",
        limit=2,
        settings=settings,
        embedder=emb,
    )
    assert hits, "expected hybrid hits"
    assert token in hits[0].text
    assert "PREFERRED_SEMANTIC" in hits[0].text
    assert "preferred.md" in hits[0].source_path
