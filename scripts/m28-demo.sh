#!/usr/bin/env bash
# M28 demo: Neo4j NEXT expand (no LLM agent required).
# Usage: ./scripts/m28-demo.sh
# Prereq: docker compose up -d neo4j (and .env from setup.sh)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "No .env found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

(
  cd "$ROOT/backend"
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a

  echo "==> 1) Unit tests (expand helpers)"
  uv run pytest -m unit tests/unit/test_m28_expand.py -q

  echo
  echo "==> 2) Integration (skip if Neo4j down)"
  uv run pytest -m integration tests/integration/test_m28_expand_live.py -v

  echo
  echo "==> 3) Library smoke: write 3 chunks, expand middle"
  uv run python - <<'PY'
from uuid import uuid4

from mini_claude_code.config import get_settings
from mini_claude_code.memory.expand import expand_chunks, format_expand_hits
from mini_claude_code.memory.ingest import TextChunk
from mini_claude_code.memory.neo4j_docs import delete_document_graph, write_document_chunks

get_settings.cache_clear()
settings = get_settings()
doc_id = f"m28-demo-{uuid4().hex[:8]}"
source = f"docs/{doc_id}.md"
chunks = [
    TextChunk(doc_id, source, 0, "prev: setup"),
    TextChunk(doc_id, source, 1, "hit: island"),
    TextChunk(doc_id, source, 2, "next: follow-up"),
]
try:
    n = write_document_chunks(chunks, settings=settings, replace=True)
    print(f"wrote {n} neo4j chunks for {doc_id}")
    hits = expand_chunks(doc_id=doc_id, chunk_index=1, radius=1, settings=settings)
    print(format_expand_hits(hits))
finally:
    delete_document_graph(doc_id, settings=settings)
    print("(cleaned demo graph)")
PY
)
