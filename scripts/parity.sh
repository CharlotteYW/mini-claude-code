#!/usr/bin/env bash
# M1 tool-calling parity harness across configured providers.
# Usage: ./scripts/parity.sh
#        ./scripts/parity.sh --provider ollama
#        ./scripts/parity.sh --provider anthropic --model claude-sonnet-4-20250514
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
  uv run mcc-tools-parity "$@"
)
