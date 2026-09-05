# M20 ingest demo

This file exists so you can **feel** the doc ingestion pipeline.

Unique marker (for search): **M20_MARKER_PURPLE_ORBIT**

Remember:

1. Chunking happens in the **ingestion pipeline**, not inside Neo4j.
2. After `ingest_docs`, semantic search (`search_chunks`) should find this marker
   and cite `docs/m20-demo.md` with a chunk index.
3. Prefer `pnpm` for JS and `uv` for Python in this learning repo.
