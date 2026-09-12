#!/usr/bin/env bash
# M37 demo: budgeted compaction unit path + optional Anthropic cache smoke.
# Usage: ./scripts/m37-demo.sh
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

  echo "==> 1) Unit tests (budget / cache markers / usage footer)"
  uv run pytest -m unit tests/unit/test_m37_prompt_cache_budget.py -q

  echo
  echo "==> 2) Integration Anthropic cache smoke (skip without ANTHROPIC_API_KEY)"
  uv run pytest -m integration tests/integration/test_m37_prompt_cache_live.py -v

  echo
  echo "==> 3) Soft-budget compact tip"
  echo "    CONTEXT_TOKEN_BUDGET=200 CONTEXT_COMPACT_THRESHOLD=10000 \\"
  echo "      uv run mcc-agent --usage -p 'say hi'   # long threads will [compact]"
)
