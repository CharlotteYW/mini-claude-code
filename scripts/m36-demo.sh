#!/usr/bin/env bash
# M36 demo: retrieval hit@k on golden corpus (+ optional agent cases).
# Usage: ./scripts/m36-demo.sh
# Prereq for retrieval: docker compose up -d postgres elasticsearch
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

  echo "==> 1) Unit tests (metrics / faithfulness / qrels)"
  uv run pytest -m unit tests/unit/test_m36_rag_eval.py -q

  echo
  echo "==> 2) Integration golden hit@k (skip if ES/Postgres down)"
  uv run pytest -m integration tests/integration/test_m36_rag_eval_live.py -v

  echo
  echo "==> 3) mcc-eval --retrieval --skip-agent-cases"
  uv run mcc-eval --retrieval --skip-agent-cases || true

  echo
  echo "==> 4) Optional full: agent cases + retrieval"
  echo "    uv run mcc-eval --retrieval"
)
