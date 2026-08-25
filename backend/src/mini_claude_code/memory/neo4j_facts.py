"""Neo4j durable facts (M8) — long-term knowledge outside the chat transcript.

Simplification: Fact nodes with text + optional kind; no full entity resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_claude_code.config import Settings, get_settings


@dataclass(frozen=True)
class MemoryFact:
    id: str
    text: str
    kind: str


def _driver(settings: Settings):
    import neo4j

    return neo4j.GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def remember_fact(
    text: str,
    *,
    kind: str = "note",
    settings: Settings | None = None,
) -> MemoryFact:
    """Create a Fact node. Returns the stored fact."""
    settings = settings or get_settings()
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("fact text must be non-empty")
    kind_clean = (kind or "note").strip() or "note"

    driver = _driver(settings)
    try:
        with driver.session() as session:
            record = session.run(
                """
                CREATE (f:Fact {
                  id: randomUUID(),
                  text: $text,
                  kind: $kind,
                  created_at: datetime()
                })
                RETURN f.id AS id, f.text AS text, f.kind AS kind
                """,
                text=cleaned,
                kind=kind_clean,
            ).single()
            if record is None:
                raise RuntimeError("Neo4j CREATE Fact returned no row")
            return MemoryFact(
                id=str(record["id"]),
                text=str(record["text"]),
                kind=str(record["kind"]),
            )
    finally:
        driver.close()


def recall_facts(
    query: str = "",
    *,
    limit: int = 10,
    settings: Settings | None = None,
) -> list[MemoryFact]:
    """Recall facts. Empty query → newest; else case-insensitive CONTAINS."""
    settings = settings or get_settings()
    limit = max(1, min(int(limit), 50))
    q = query.strip()

    driver = _driver(settings)
    try:
        with driver.session() as session:
            if q:
                result = session.run(
                    """
                    MATCH (f:Fact)
                    WHERE toLower(f.text) CONTAINS toLower($q)
                       OR toLower(f.kind) CONTAINS toLower($q)
                    RETURN f.id AS id, f.text AS text, f.kind AS kind
                    ORDER BY f.created_at DESC
                    LIMIT $limit
                    """,
                    q=q,
                    limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (f:Fact)
                    RETURN f.id AS id, f.text AS text, f.kind AS kind
                    ORDER BY f.created_at DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )
            return [
                MemoryFact(
                    id=str(r["id"]),
                    text=str(r["text"]),
                    kind=str(r["kind"]),
                )
                for r in result
            ]
    finally:
        driver.close()


def format_facts_for_prompt(facts: list[MemoryFact]) -> str:
    if not facts:
        return ""
    lines = [f"- ({f.kind}) {f.text}" for f in facts]
    return "[durable facts from Neo4j]\n" + "\n".join(lines)


def recall_facts_block(
    query: str = "",
    *,
    limit: int = 8,
    settings: Settings | None = None,
) -> str:
    """Best-effort recall for injection; empty string if Neo4j unavailable."""
    try:
        facts = recall_facts(query, limit=limit, settings=settings)
    except Exception:  # noqa: BLE001
        return ""
    return format_facts_for_prompt(facts)
