#!/usr/bin/env bash
# Run the ReAct agent (M2+ tools; M5 durable sessions).
# Usage: ./scripts/agent.sh "prompt"
#        ./scripts/agent.sh --thread-id demo-1 "Remember ORANGE"
#        ./scripts/agent.sh --repl --thread-id demo-1
#        ./scripts/agent.sh --checkpointer memory --thread-id local-1 "hi"
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
