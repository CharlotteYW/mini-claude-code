#!/usr/bin/env bash
# M21 demo: ingest docs → Elasticsearch BM25 keyword search (no LLM agent).
# Usage: ./scripts/m21-demo.sh
# Prereq: docker compose up -d elasticsearch  (and ideally postgres/neo4j for full ingest)
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

  echo "==> 1) Unit tests (offline ES serializers)"
  uv run pytest -m unit tests/unit/test_m21_elasticsearch.py -q

  echo
  echo "==> 2) Ingest workspace/docs (prefer ES; other stores best-effort)"
  uv run python - <<'PY'
from mini_claude_code.config import get_settings, resolve_workspace_root
from mini_claude_code.memory.pipeline import ingest_paths

get_settings.cache_clear()
settings = get_settings()
root = resolve_workspace_root(settings)
print(f"workspace: {root}")
result = ingest_paths("docs", workspace_root=root, settings=settings)
print(result.summary())
if not result.chunks:
    raise SystemExit(1)
if result.elasticsearch_written == 0:
    print("ERROR: Elasticsearch wrote 0 docs. Is mcc-elasticsearch up?")
    print("  docker compose --env-file .env up -d elasticsearch")
    raise SystemExit(1)
if result.errors:
    print("(partial write — see ERROR lines above)")
PY

  echo
  echo "==> 3) search_keyword (BM25) for marker: ${MARKER}"
  uv run python - <<PY
from mini_claude_code.config import get_settings
from mini_claude_code.memory.elasticsearch_chunks import search_keyword
from mini_claude_code.memory.pgvector_chunks import search_chunks

get_settings.cache_clear()
settings = get_settings()
marker = "${MARKER}"

print("--- Elasticsearch BM25 ---")
hits = search_keyword(marker, limit=3, settings=settings)
for h in hits:
    score = f"{h.score:.3f}" if h.score is not None else "?"
    print(f"  [{h.source_path}#{h.chunk_index} score={score}] {h.text[:160]!r}")
if not hits:
    raise SystemExit("no ES hits")

print("--- pgvector semantic (contrast) ---")
try:
    for h in search_chunks(marker, limit=3, settings=settings):
        score = f"{h.score:.3f}" if h.score is not None else "?"
        print(f"  [{h.source_path}#{h.chunk_index} score={score}] {h.text[:160]!r}")
except Exception as exc:
    print(f"  (skip: {exc})")
PY

  echo
  echo "==> 4) Optional agent:"
  echo "  ./scripts/agent.sh \"ingest_docs on docs/ then search_keyword for ${MARKER}\""
  echo
  echo "Done. curl http://localhost:9200/mcc_chunks/_count"
)
