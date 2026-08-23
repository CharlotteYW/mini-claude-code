#!/usr/bin/env bash
# Run the M2 ReAct agent.
# Usage: ./scripts/agent.sh
#        ./scripts/agent.sh "Use the add tool to compute 3 + 4"
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
  uv run mcc-agent "$@"
)
