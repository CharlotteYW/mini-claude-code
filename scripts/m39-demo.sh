#!/usr/bin/env bash
# M39 demo: observation budget unit + graph truncation.
# Usage: ./scripts/m39-demo.sh
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

  echo "==> 1) Unit tests (truncate / summarize / PolicyToolNode)"
  uv run pytest -m unit tests/unit/test_m39_observation_budget.py -q

  echo
  echo "==> 2) Integration: graph truncates huge ToolMessage"
  uv run pytest -m integration tests/integration/test_m39_observation_budget_live.py -v

  echo
  echo "==> 3) Tip"
  echo "    TOOL_OBSERVATION_MAX_CHARS=500 uv run mcc-agent -p 'run_shell: seq 1 5000'"
)
