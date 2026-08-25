"""M8-B unit tests: pgvector helpers with a fake embedder (no Ollama/DB write path for pure helpers)."""

from __future__ import annotations

import hashlib
from typing import Sequence

import pytest

from mini_claude_code.memory.pgvector_notes import _vector_literal

pytestmark = pytest.mark.unit


class _FakeEmbedder:
    """Deterministic 8-d vectors for unit tests (not used against real pgvector dim)."""

    dim: int = 8

    def embed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        vals = [b / 255.0 for b in digest[: self.dim]]
        return vals


def test_vector_literal_format() -> None:
    lit = _vector_literal([0.1, -0.2, 0.3])
    assert lit.startswith("[")
    assert lit.endswith("]")
    assert "0.10000000" in lit


def test_fake_embedder_is_stable() -> None:
    emb = _FakeEmbedder()
    a = emb.embed_query("auth timeout")
    b = emb.embed_query("auth timeout")
    c = emb.embed_query("something else")
    assert a == b
    assert a != c
    assert len(a) == 8
