#!/usr/bin/env bash
# Slack OAuth install + Socket Mode agent bot (M18).
# Usage: ./scripts/slack.sh install
#        ./scripts/slack.sh run
#        ./scripts/slack.sh run --checkpointer memory   # no Postgres required
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
  uv run mcc-slack "$@"
)
