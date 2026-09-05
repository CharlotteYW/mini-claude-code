"""LangChain tools for Neo4j facts + pgvector notes + doc ingest (M8/M20/M21)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.elasticsearch_chunks import search_keyword
from mini_claude_code.memory.neo4j_docs import search_chunks_keyword
from mini_claude_code.memory.neo4j_facts import recall_facts, remember_fact
from mini_claude_code.memory.pgvector_chunks import search_chunks
from mini_claude_code.memory.pgvector_notes import recall_notes, remember_note
from mini_claude_code.memory.pipeline import ingest_paths


def build_memory_tools(
    settings: Settings | None = None,
    *,
    workspace_root: Path | None = None,
) -> list:
    """Neo4j fact tools + pgvector notes + ingest/search (semantic + keyword)."""
    settings = settings or get_settings()
    from mini_claude_code.config import resolve_workspace_root

    root = (
        workspace_root.expanduser().resolve()
        if workspace_root is not None
        else resolve_workspace_root(settings)
    )

    @tool
    def remember_fact_tool(text: str, kind: str = "note") -> str:
        """Store a durable project fact in Neo4j (survives new threads and compaction).

        Use for stable preferences and project truths the user wants remembered
        long-term — not for transient chat. Examples: package manager, service
        ownership, coding conventions.
        """
        try:
            fact = remember_fact(text, kind=kind, settings=settings)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR remembering fact: {exc}"
        return f"stored fact id={fact.id} kind={fact.kind}: {fact.text}"

    @tool
    def recall_facts_tool(query: str = "", limit: int = 10) -> str:
        """Recall durable Neo4j facts. Empty query returns newest facts.

        Use when answering needs project knowledge that may not be in the
        current chat transcript (e.g. after compaction or a new thread).
        """
        try:
            facts = recall_facts(query, limit=limit, settings=settings)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR recalling facts: {exc}"
        if not facts:
            return "No matching facts."
        return "\n".join(f"- [{f.kind}] {f.text} (id={f.id})" for f in facts)

    @tool
    def remember_note_tool(text: str) -> str:
        """Store a free-form note in Postgres pgvector for semantic (fuzzy) recall.

        Prefer this for prose/notes you may later ask about in different words.
        Prefer remember_fact for crisp project truths (preferences, ownership).
        Requires a local Ollama embedding model (EMBEDDING_MODEL).
        """
        try:
            note = remember_note(text, settings=settings)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR remembering note: {exc}"
        return f"stored note id={note.id}: {note.text}"

    @tool
    def recall_notes_tool(query: str, limit: int = 5) -> str:
        """Semantically search pgvector notes by meaning (not exact keywords).

        Ask in natural language; nearest embeddings are returned. Empty query
        is not allowed — use a phrase describing what you need.
        """
        try:
            notes = recall_notes(query, limit=limit, settings=settings)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR recalling notes: {exc}"
        if not notes:
            return "No matching notes."
        lines = []
        for n in notes:
            score = f" score={n.score:.3f}" if n.score is not None else ""
            lines.append(f"- {n.text} (id={n.id}{score})")
        return "\n".join(lines)

    @tool
    def ingest_docs_tool(path: str) -> str:
        """Ingest workspace markdown/text into pgvector + Neo4j + Elasticsearch.

        ``path`` is a file, directory, or glob under the workspace (e.g. docs/
        or docs/*.md). Cleans, chunks, embeds, and writes Document/Chunk nodes,
        memory_chunks rows, and the ES ``mcc_chunks`` index. Re-ingest replaces
        prior chunks for the same source path. Prefer this over remember_note
        for whole docs.
        """
        try:
            result = ingest_paths(path, workspace_root=root, settings=settings)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR ingesting: {exc}"
        return result.summary()

    @tool
    def search_chunks_tool(query: str, limit: int = 5) -> str:
        """Semantically search ingested document chunks (pgvector) by meaning.

        Returns text with source_path and chunk_index for citation. Use after
        ingest_docs. Prefer search_keyword for exact tokens / error codes.
        For ad-hoc blurbs use recall_notes; for crisp facts use recall_facts.
        """
        try:
            hits = search_chunks(query, limit=limit, settings=settings)
        except Exception as exc:  # noqa: BLE001
            try:
                kw = search_chunks_keyword(query, limit=limit, settings=settings)
            except Exception as exc2:  # noqa: BLE001
                return f"ERROR searching chunks: {exc}; neo4j fallback: {exc2}"
            if not kw:
                return f"ERROR searching chunks: {exc} (no neo4j keyword hits)"
            lines = [
                f"- [{h.source_path}#{h.chunk_index}] {h.text[:400]}"
                f" (keyword fallback title={h.title!r})"
                for h in kw
            ]
            return "\n".join(lines)
        if not hits:
            return "No matching chunks. Try ingest_docs on workspace docs first."
        lines = []
        for h in hits:
            score = f" score={h.score:.3f}" if h.score is not None else ""
            title = f" title={h.title!r}" if h.title else ""
            lines.append(
                f"- [{h.source_path}#{h.chunk_index}{title}{score}] {h.text}"
            )
        return "\n".join(lines)

    @tool
    def search_keyword_tool(query: str, limit: int = 5) -> str:
        """Full-text / BM25 search over ingested chunks in Elasticsearch.

        Prefer this for exact markers, error codes, and must-contain tokens.
        Prefer search_chunks when the user paraphrases and meaning matters more
        than exact wording. Requires Compose Elasticsearch and prior ingest_docs.
        """
        try:
            hits = search_keyword(query, limit=limit, settings=settings)
        except Exception as exc:  # noqa: BLE001
            return f"ERROR search_keyword: {exc}"
        if not hits:
            return "No keyword hits. Try ingest_docs first or a more exact token."
        lines = []
        for h in hits:
            score = f" score={h.score:.3f}" if h.score is not None else ""
            title = f" title={h.title!r}" if h.title else ""
            lines.append(
                f"- [{h.source_path}#{h.chunk_index}{title}{score}] {h.text}"
            )
        return "\n".join(lines)

    remember_fact_tool.name = "remember_fact"
    recall_facts_tool.name = "recall_facts"
    remember_note_tool.name = "remember_note"
    recall_notes_tool.name = "recall_notes"
    ingest_docs_tool.name = "ingest_docs"
    search_chunks_tool.name = "search_chunks"
    search_keyword_tool.name = "search_keyword"
    return [
        remember_fact_tool,
        recall_facts_tool,
        remember_note_tool,
        recall_notes_tool,
        ingest_docs_tool,
        search_chunks_tool,
        search_keyword_tool,
    ]
