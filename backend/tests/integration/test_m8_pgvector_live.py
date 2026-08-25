"""M8-B integration: pgvector remember/recall (skip if Postgres or embed model down)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.pgvector_notes import (
    create_ollama_embedder,
    recall_notes,
    remember_note,
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
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")


def _embedder_or_skip(settings: Settings):
    try:
        emb = create_ollama_embedder(settings)
        vec = emb.embed_query("ping")
        if len(vec) != settings.embedding_dimensions:
            pytest.skip(
                f"embedding dim {len(vec)} != {settings.embedding_dimensions}; "
                f"pull/adjust EMBEDDING_MODEL={settings.embedding_model}"
            )
        return emb
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"Ollama embeddings unavailable ({exc}). "
            f"Try: ollama pull {settings.embedding_model}"
        )


def test_remember_and_semantic_recall_note() -> None:
    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    embedder = _embedder_or_skip(settings)

    token = f"m8b-{uuid4().hex[:8]}"
    text = (
        f"Operational note {token}: the auth service uses a 30 second "
        "timeout when talking to Redis."
    )
    stored = remember_note(text, settings=settings, embedder=embedder)
    assert stored.id

    # Different wording — should still rank the note highly if embeddings work.
    hits = recall_notes(
        f"How long does authentication wait on Redis? code {token}",
        limit=5,
        settings=settings,
        embedder=embedder,
    )
    assert any(token in n.text for n in hits), hits


def test_pgvector_roundtrip_with_fake_embedder() -> None:
    """Exercises SQL + schema without requiring an Ollama embed model."""
    import hashlib

    settings = _load_repo_settings()
    _postgres_or_skip(settings)
    dim = settings.embedding_dimensions

    class _Fake:
        def embed_query(self, text: str) -> list[float]:
            digest = hashlib.sha256(text.encode()).digest()
            # Expand/repeat digest bytes to requested dim.
            vals: list[float] = []
            while len(vals) < dim:
                for b in digest:
                    vals.append(b / 255.0)
                    if len(vals) >= dim:
                        break
            return vals[:dim]

    emb = _Fake()
    token = f"fake-{uuid4().hex[:8]}"
    remember_note(f"note about widgets {token}", settings=settings, embedder=emb)
    hits = recall_notes(
        f"widgets {token}", limit=3, settings=settings, embedder=emb
    )
    assert any(token in n.text for n in hits), hits
