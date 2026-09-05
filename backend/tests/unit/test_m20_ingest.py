"""M20 unit tests: clean/chunk/metadata + permissions (no DB)."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.agent.permissions import default_mode_for, resolve_permission
from mini_claude_code.memory.ingest import (
    chunk_text,
    clean_text,
    doc_id_for_path,
    extract_title,
    resolve_ingest_paths,
)
from mini_claude_code.memory.pipeline import ingest_paths
from mini_claude_code.tools.memory_tools import build_memory_tools

pytestmark = pytest.mark.unit


def test_clean_text_normalizes_newlines_and_blank_runs() -> None:
    raw = "a  \r\n\r\n\r\n\r\nb\r\n"
    assert clean_text(raw) == "a\n\nb"


def test_chunk_short_doc_one_chunk() -> None:
    chunks = chunk_text(
        "hello world",
        doc_id="doc-x",
        source_path="docs/a.md",
        chunk_size=100,
        chunk_overlap=10,
    )
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].text == "hello world"
    assert chunks[0].source_path == "docs/a.md"


def test_chunk_size_overlap_boundaries() -> None:
    body = "ABCDEFGHIJ" * 20  # 200 chars
    chunks = chunk_text(
        body,
        doc_id="doc-y",
        source_path="docs/long.txt",
        chunk_size=50,
        chunk_overlap=10,
    )
    assert len(chunks) >= 4
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Overlap: next start should re-include last 10 of previous when possible.
    assert chunks[0].text[-10:] in chunks[1].text


def test_empty_input_no_chunks() -> None:
    assert chunk_text("   \n\n  ", doc_id="d", source_path="x.md") == []


def test_extract_title_h1() -> None:
    assert extract_title("# Shipping\n\nbody") == "Shipping"


def test_doc_id_stable() -> None:
    assert doc_id_for_path("docs/a.md") == doc_id_for_path("docs/a.md")
    assert doc_id_for_path("docs/a.md") != doc_id_for_path("docs/b.md")


def test_resolve_ingest_paths_dir(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# A\n\none\n", encoding="utf-8")
    (docs / "b.txt").write_text("two\n", encoding="utf-8")
    (docs / "skip.py").write_text("x=1\n", encoding="utf-8")
    paths = resolve_ingest_paths(tmp_path, "docs")
    names = {p.name for p in paths}
    assert names == {"a.md", "b.txt"}


def test_ingest_paths_offline_no_stores(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text(
        "# Title\n\n" + ("word " * 200), encoding="utf-8"
    )
    result = ingest_paths(
        "docs/note.md",
        workspace_root=tmp_path,
        write_pgvector=False,
        write_neo4j=False,
        chunk_size=80,
        chunk_overlap=10,
    )
    assert not result.errors
    assert result.files == ["docs/note.md"]
    assert len(result.chunks) > 1
    assert result.pgvector_written == 0
    assert result.neo4j_written == 0


def test_ingest_escape_rejected(tmp_path: Path) -> None:
    result = ingest_paths(
        "../outside.md",
        workspace_root=tmp_path,
        write_pgvector=False,
        write_neo4j=False,
    )
    assert result.errors
    assert result.chunks == []


def test_permission_modes_ingest_search() -> None:
    assert default_mode_for("search_chunks") == "auto"
    assert default_mode_for("ingest_docs") == "ask"
    assert resolve_permission("ingest_docs", plan_mode=True) == "deny"
    assert resolve_permission("search_chunks", plan_mode=True) == "auto"


def test_memory_tools_include_ingest_search(tmp_path: Path) -> None:
    tools = build_memory_tools(workspace_root=tmp_path)
    names = {t.name for t in tools}
    assert "ingest_docs" in names
    assert "search_chunks" in names


def test_fake_llm_ingest_tool_call(tmp_path: Path) -> None:
    """Graph can invoke ingest_docs without live DB (writes disabled via stub)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("# X\n\nhello ingest\n", encoding="utf-8")

    calls: list[str] = []

    @tool
    def ingest_docs(path: str) -> str:
        """Ingest docs under workspace."""
        calls.append(path)
        r = ingest_paths(
            path,
            workspace_root=tmp_path,
            write_pgvector=False,
            write_neo4j=False,
        )
        return r.summary()

    ingest_docs.name = "ingest_docs"

    class _LLM:
        def bind_tools(self, _tools: object) -> "_LLM":
            return self

        def invoke(self, messages: list, config: object = None) -> AIMessage:
            # After tool result, finish.
            if any(isinstance(m, ToolMessage) for m in messages):
                return AIMessage(content="done")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ingest_docs",
                        "args": {"path": "docs"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )

    g = StateGraph(MessagesState)
    llm = _LLM()

    def call_model(state: MessagesState) -> dict:
        return {"messages": [llm.invoke(state["messages"])]}

    g.add_node("call_model", call_model)
    g.add_node("tools", ToolNode([ingest_docs]))
    g.add_edge(START, "call_model")

    def route(state: MessagesState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    g.add_conditional_edges("call_model", route, {"tools": "tools", END: END})
    g.add_edge("tools", "call_model")
    app = g.compile()
    out = app.invoke(
        {"messages": [HumanMessage(content="ingest docs")]},
        config={"recursion_limit": 8},
    )
    assert calls == ["docs"]
    assert any(isinstance(m, ToolMessage) and "chunks=" in str(m.content) for m in out["messages"])
