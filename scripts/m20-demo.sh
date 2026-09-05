#!/usr/bin/env bash
# M20 demo: ingest workspace/docs → search for a known marker (no LLM agent).
# Usage: ./scripts/m20-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "No .env found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

MARKER="M20_MARKER_PURPLE_ORBIT"

(
  cd "$ROOT/backend"
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a

  echo "==> 1) Unit tests (offline pipeline)"
  uv run pytest -m unit tests/unit/test_m20_ingest.py -q

  echo
  echo "==> 2) Ingest workspace/docs (pgvector + Neo4j)"
  uv run python - <<'PY'
from pathlib import Path
from mini_claude_code.config import get_settings, resolve_workspace_root
from mini_claude_code.memory.pipeline import ingest_paths

get_settings.cache_clear()
settings = get_settings()
root = resolve_workspace_root(settings)
print(f"workspace: {root}")
result = ingest_paths("docs", workspace_root=root, settings=settings)
print(result.summary())
# Soft-fail: Neo4j-only still teaches pipeline; pgvector needs embed model.
if not result.chunks:
    raise SystemExit(1)
if result.errors and result.neo4j_written == 0 and result.pgvector_written == 0:
    raise SystemExit(1)
if result.errors:
    print("(continuing with partial write — see ERROR lines above)")
PY

  echo
  echo "==> 3) Search for marker: ${MARKER}"
  uv run python - <<PY
from mini_claude_code.config import get_settings
from mini_claude_code.memory.pgvector_chunks import search_chunks
from mini_claude_code.memory.neo4j_docs import search_chunks_keyword

get_settings.cache_clear()
settings = get_settings()
marker = "${MARKER}"

print("--- Neo4j keyword ---")
try:
    for h in search_chunks_keyword(marker, limit=3, settings=settings):
        print(f"  [{h.source_path}#{h.chunk_index}] {h.text[:160]!r}")
except Exception as exc:
    print(f"  (skip/fail: {exc})")

print("--- pgvector semantic ---")
try:
    hits = search_chunks(marker, limit=3, settings=settings)
    for h in hits:
        score = f"{h.score:.3f}" if h.score is not None else "?"
        print(f"  [{h.source_path}#{h.chunk_index} score={score}] {h.text[:160]!r}")
    if not hits:
        print("  (no hits)")
except Exception as exc:
    print(f"  (need Ollama embed model — try: ollama pull nomic-embed-text)")
    print(f"  detail: {exc}")
PY

  echo
  echo "==> 4) Optional agent path (LLM decides to call tools):"
  echo "  ./scripts/agent.sh \"Use ingest_docs on docs/ then search_chunks for ${MARKER}\""
  echo "  (omit --plan: ingest_docs is ask / denied in Plan Mode)"
  echo
  echo "Done. Inspect stores: ./scripts/db-inspect.sh"
)
