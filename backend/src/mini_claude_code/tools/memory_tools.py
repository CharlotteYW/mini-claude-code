"""LangChain tools for Neo4j durable facts (M8)."""

from __future__ import annotations

from langchain_core.tools import tool

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.neo4j_facts import recall_facts, remember_fact


def build_memory_tools(settings: Settings | None = None) -> list:
    """remember_fact / recall_facts bound to current Settings."""
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

    # Expose stable names for the model / ToolNode.
    remember_fact_tool.name = "remember_fact"
    recall_facts_tool.name = "recall_facts"
    return [remember_fact_tool, recall_facts_tool]
