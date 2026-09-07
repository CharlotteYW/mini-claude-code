#!/usr/bin/env bash
# M27 demo: hybrid ES → pgvector (no LLM agent required).
# Usage: ./scripts/m27-demo.sh
# Prereq: docker compose up -d postgres elasticsearch; Ollama embeddings optional
#         (demo uses ingest + library search_hybrid).
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

  echo "==> 1) Unit tests (hybrid helpers)"
  uv run pytest -m unit tests/unit/test_m27_hybrid.py -q

  echo
  echo "==> 2) Integration (skip if ES/Postgres down)"
  uv run pytest -m integration tests/integration/test_m27_hybrid_live.py -v

  echo
  echo "==> 3) Library smoke on workspace/docs (best-effort)"
  uv run python - <<'PY'
from mini_claude_code.config import get_settings, resolve_workspace_root
from mini_claude_code.memory.hybrid import search_hybrid
from mini_claude_code.memory.pipeline import ingest_paths

get_settings.cache_clear()
settings = get_settings()
root = resolve_workspace_root(settings)
print(f"workspace: {root}")
try:
    result = ingest_paths("docs", workspace_root=root, settings=settings)
    print(result.summary())
except Exception as exc:
    print(f"ingest skipped/failed: {exc}")
    raise SystemExit(0)

try:
    hits = search_hybrid("documentation marker", limit=3, settings=settings)
except Exception as exc:
    print(f"search_hybrid failed: {exc}")
    raise SystemExit(0)

if not hits:
    print("No hybrid hits (empty keyword stage or no overlap).")
else:
    for h in hits:
        print(f"- [{h.source_path}#{h.chunk_index} score={h.score}] {h.text[:120]!r}")
PY
)
