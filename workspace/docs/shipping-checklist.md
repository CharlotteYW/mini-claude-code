# Shipping checklist

Use this note when preparing a local quality gate before opening a PR.

The mini-claude-code agent can run `ship_check` (ruff + unit tests) and optionally
gate `open_pull_request` when `SHIP_REQUIRE_GREEN=1`.

Remember: chunking happens in the **ingestion pipeline**, not inside Neo4j.
Neo4j stores Document/Chunk nodes after ingest; pgvector stores embeddings for
semantic search via `search_chunks`.
