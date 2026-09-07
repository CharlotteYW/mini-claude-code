"""M28 unit tests: expand window helpers + tool registration (no Neo4j)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mini_claude_code.agent.permissions import default_mode_for, resolve_permission
from mini_claude_code.memory.expand import (
    clamp_radius,
    expand_chunks,
    expand_index_window,
    format_chunk_citation,
    format_expand_hits,
    parse_chunk_ref,
)
from mini_claude_code.memory.neo4j_docs import GraphChunkHit
from mini_claude_code.tools.memory_tools import build_memory_tools

pytestmark = pytest.mark.unit


def test_clamp_radius_default_and_bounds() -> None:
    assert clamp_radius(0) == 1
    assert clamp_radius(-2) == 1
    assert clamp_radius(1) == 1
    assert clamp_radius(2) == 2
    assert clamp_radius(3) == 3
    assert clamp_radius(99) == 3
    assert clamp_radius("nope") == 1  # type: ignore[arg-type]


def test_expand_index_window_middle_and_edges() -> None:
    assert expand_index_window(2, 1, max_index=4) == [1, 2, 3]
    assert expand_index_window(0, 1, max_index=4) == [0, 1]
    assert expand_index_window(4, 1, max_index=4) == [3, 4]
    assert expand_index_window(1, 2, max_index=2) == [0, 1, 2]
    assert expand_index_window(5, 1, min_index=0, max_index=2) == []


def test_parse_chunk_ref_from_pair_or_id() -> None:
    assert parse_chunk_ref(doc_id="doc-a", chunk_index=2) == ("doc-a", 2)
    assert parse_chunk_ref(chunk_id="doc-a:2") == ("doc-a", 2)
    assert parse_chunk_ref(chunk_id="ns:doc:3") == ("ns:doc", 3)
    with pytest.raises(ValueError, match="doc_id"):
        parse_chunk_ref(chunk_index=0)
    with pytest.raises(ValueError, match="chunk_id"):
        parse_chunk_ref(chunk_id="no-colon")


def test_format_citations_ordered() -> None:
    hits = [
        GraphChunkHit("a:0", "a", "docs/x.md", 0, "alpha", title="T"),
        GraphChunkHit("a:1", "a", "docs/x.md", 1, "beta"),
    ]
    assert format_chunk_citation(hits[0]) == "docs/x.md#0"
    text = format_expand_hits(hits)
    assert "[docs/x.md#0 title='T'] alpha" in text
    assert "[docs/x.md#1] beta" in text
    assert format_expand_hits([]) == "No chunks in expand window."


def test_expand_chunks_delegates_parsed_ref() -> None:
    fake = [
        GraphChunkHit("d:1", "d", "p.md", 1, "mid"),
    ]
    with patch(
        "mini_claude_code.memory.expand.expand_chunks_via_next",
        return_value=fake,
    ) as walk:
        out = expand_chunks(chunk_id="d:1", radius=1)
    assert out == fake
    walk.assert_called_once()
    kwargs = walk.call_args.kwargs
    assert kwargs["doc_id"] == "d"
    assert kwargs["chunk_index"] == 1
    assert kwargs["radius"] == 1


def test_expand_chunks_permission_and_registration() -> None:
    assert default_mode_for("expand_chunks") == "auto"
    assert resolve_permission("expand_chunks", plan_mode=True) == "auto"
    tools = build_memory_tools(workspace_root=Path("/tmp"))
    names = {t.name for t in tools}
    assert "expand_chunks" in names
