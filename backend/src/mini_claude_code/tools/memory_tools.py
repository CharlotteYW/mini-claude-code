"""LangChain tools for Neo4j facts + pgvector notes (M8)."""

from __future__ import annotations

from langchain_core.tools import tool

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.neo4j_facts import recall_facts, remember_fact
from mini_claude_code.memory.pgvector_notes import recall_notes, remember_note


def build_memory_tools(settings: Settings | None = None) -> list:
    """Neo4j fact tools + pgvector semantic note tools."""
    settings = settings or get_settings()

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

    remember_fact_tool.name = "remember_fact"
    recall_facts_tool.name = "recall_facts"
    remember_note_tool.name = "remember_note"
    recall_notes_tool.name = "recall_notes"
    return [
        remember_fact_tool,
        recall_facts_tool,
        remember_note_tool,
        recall_notes_tool,
    ]
