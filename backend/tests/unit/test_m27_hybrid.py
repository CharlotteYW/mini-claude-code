"""M27 unit tests: hybrid key join + re-rank (no live ES/Postgres)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mini_claude_code.agent.permissions import default_mode_for, resolve_permission
from mini_claude_code.memory.elasticsearch_chunks import KeywordChunkHit
from mini_claude_code.memory.hybrid import (
    keys_from_keyword_hits,
    rerank_hits_by_score,
    search_hybrid,
)
from mini_claude_code.memory.pgvector_chunks import MemoryChunkHit
from mini_claude_code.tools.memory_tools import build_memory_tools

pytestmark = pytest.mark.unit


def test_keys_from_keyword_hits_dedupe_preserve_order() -> None:
    hits = [
        KeywordChunkHit("a:0", "a", "x.md", 0, "t0", score=3.0),
        KeywordChunkHit("b:1", "b", "y.md", 1, "t1", score=2.0),
        KeywordChunkHit("a:0", "a", "x.md", 0, "t0-dup", score=1.0),
    ]
    assert keys_from_keyword_hits(hits) == [("a", 0), ("b", 1)]


def test_rerank_hits_by_score_orders_and_limits() -> None:
    hits = [
        MemoryChunkHit("u1", "a", "x.md", 0, "low", score=0.1),
        MemoryChunkHit("u2", "b", "y.md", 1, "high", score=0.9),
        MemoryChunkHit("u3", "c", "z.md", 2, "mid", score=0.5),
        MemoryChunkHit("u4", "d", "w.md", 3, "none", score=None),
    ]
    out = rerank_hits_by_score(hits, limit=2)
    assert [h.doc_id for h in out] == ["b", "c"]
    assert out[0].score == 0.9


def test_search_hybrid_empty_es_returns_empty_no_vector_call() -> None:
    with (
        patch(
            "mini_claude_code.memory.hybrid.search_keyword",
            return_value=[],
        ) as es,
        patch(
            "mini_claude_code.memory.hybrid.search_chunks_among",
        ) as among,
    ):
        out = search_hybrid("anything", limit=3)
    assert out == []
    es.assert_called_once()
    among.assert_not_called()


def test_search_hybrid_joins_on_doc_id_chunk_index_not_uuid() -> None:
    kw = [
        KeywordChunkHit("doc-1:0", "doc-1", "a.md", 0, "alpha TOKEN", score=5.0),
        KeywordChunkHit("doc-2:1", "doc-2", "b.md", 1, "beta", score=4.0),
    ]
    vec = [
        MemoryChunkHit("uuid-b", "doc-2", "b.md", 1, "beta", score=0.2),
        MemoryChunkHit("uuid-a", "doc-1", "a.md", 0, "alpha TOKEN", score=0.8),
    ]
    with (
        patch(
            "mini_claude_code.memory.hybrid.search_keyword",
            return_value=kw,
        ),
        patch(
            "mini_claude_code.memory.hybrid.search_chunks_among",
            return_value=vec,
        ) as among,
    ):
        out = search_hybrid("TOKEN paraphrase", limit=2)
    # among received keys from ES, not UUIDs
    keys = among.call_args.args[1]
    assert keys == [("doc-1", 0), ("doc-2", 1)]
    assert [h.id for h in out] == ["uuid-a", "uuid-b"]
    assert out[0].doc_id == "doc-1"


def test_permission_search_hybrid_auto() -> None:
    assert default_mode_for("search_hybrid") == "auto"
    assert resolve_permission("search_hybrid", plan_mode=False) == "auto"
    assert resolve_permission("search_hybrid", plan_mode=True) == "auto"


def test_memory_tools_include_search_hybrid(tmp_path: Path) -> None:
    names = {t.name for t in build_memory_tools(workspace_root=tmp_path)}
    assert "search_hybrid" in names
    assert "search_keyword" in names
    assert "search_chunks" in names
