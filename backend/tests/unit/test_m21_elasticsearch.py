"""M21 unit tests: ES serializers / query builders / permissions (no live ES)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_claude_code.agent.permissions import default_mode_for, resolve_permission
from mini_claude_code.memory.elasticsearch_chunks import (
    CHUNK_INDEX_MAPPINGS,
    build_keyword_query,
    chunk_document_id,
    chunk_to_es_document,
)
from mini_claude_code.memory.ingest import TextChunk
from mini_claude_code.memory.pipeline import ingest_paths
from mini_claude_code.tools.memory_tools import build_memory_tools

pytestmark = pytest.mark.unit


def test_chunk_to_es_document_shape() -> None:
    chunk = TextChunk(
        doc_id="doc-abc",
        source_path="docs/a.md",
        chunk_index=2,
        text="hello BM25",
        title="Title",
    )
    body = chunk_to_es_document(chunk)
    assert body == {
        "doc_id": "doc-abc",
        "source_path": "docs/a.md",
        "chunk_index": 2,
        "title": "Title",
        "text": "hello BM25",
    }
    assert chunk_document_id(chunk) == "doc-abc:2"


def test_mapping_has_text_and_keyword_fields() -> None:
    props = CHUNK_INDEX_MAPPINGS["properties"]
    assert props["doc_id"]["type"] == "keyword"
    assert props["text"]["type"] == "text"
    assert props["title"]["type"] == "text"


def test_build_keyword_query_multi_match() -> None:
    q = build_keyword_query("M20_MARKER_PURPLE_ORBIT")
    assert "multi_match" in q
    assert q["multi_match"]["query"] == "M20_MARKER_PURPLE_ORBIT"
    assert "title^2" in q["multi_match"]["fields"]
    assert "text" in q["multi_match"]["fields"]


def test_permission_search_keyword_auto() -> None:
    assert default_mode_for("search_keyword") == "auto"
    assert resolve_permission("search_keyword", plan_mode=True) == "auto"
    assert resolve_permission("ingest_docs", plan_mode=True) == "deny"


def test_memory_tools_include_search_keyword(tmp_path: Path) -> None:
    names = {t.name for t in build_memory_tools(workspace_root=tmp_path)}
    assert "search_keyword" in names
    assert "search_chunks" in names


def test_ingest_skips_elasticsearch_when_disabled(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n\nhello\n", encoding="utf-8")
    result = ingest_paths(
        "docs",
        workspace_root=tmp_path,
        write_pgvector=False,
        write_neo4j=False,
        write_elasticsearch=False,
    )
    assert not result.errors
    assert result.elasticsearch_written == 0
    assert len(result.chunks) >= 1
