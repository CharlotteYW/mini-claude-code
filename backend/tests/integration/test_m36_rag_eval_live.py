"""M36 integration: golden corpus retrieval hit@k (skip if services down)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.eval.faithfulness import check_faithfulness
from mini_claude_code.eval.retrieval import (
    default_corpus_dir,
    default_qrels_path,
    run_retrieval_eval,
)

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
    class _Bias:
        def embed_query(self, text: str) -> list[float]:
            vec = [0.0] * dim
            lower = text.lower()
            if "preferred_semantic" in lower or "preferred topic" in lower:
                vec[0] = 1.0
            else:
                vec[1] = 1.0
            return vec

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [self.embed_query(t) for t in texts]

    return _Bias()


def test_golden_corpus_keyword_and_hybrid_hit_at_k(tmp_path: Path) -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    _es_or_skip(settings)
    emb = _bias_embedder(settings.embedding_dimensions)

    report = run_retrieval_eval(
        workspace=tmp_path,
        corpus_dir=default_corpus_dir(),
        qrels_path=default_qrels_path(),
        settings=settings,
        embedder=emb,
    )
    by_id = {r.id: r for r in report.results}
    assert "keyword_exact_marker" in by_id
    assert by_id["keyword_exact_marker"].passed, by_id["keyword_exact_marker"].reason
    assert "hybrid_preferred_semantic" in by_id
    assert by_id["hybrid_preferred_semantic"].passed, by_id[
        "hybrid_preferred_semantic"
    ].reason

    # Faithfulness against retrieved evidence text for keyword case
    from mini_claude_code.memory.elasticsearch_chunks import search_keyword

    hits = search_keyword("M36_MARKER_PURPLE_ORBIT", limit=3, settings=settings)
    texts = [h.text for h in hits]
    faith = check_faithfulness(
        "Answer cites M36_MARKER_PURPLE_ORBIT",
        texts,
        required_spans=["M36_MARKER_PURPLE_ORBIT"],
    )
    assert faith.passed
