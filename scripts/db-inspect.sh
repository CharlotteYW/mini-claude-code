#!/usr/bin/env bash
# Inspect Compose-backed stores: Postgres checkpointer + Neo4j.
#
# Usage:
#   ./scripts/db-inspect.sh
#   ./scripts/db-inspect.sh postgres
#   ./scripts/db-inspect.sh neo4j
#   ./scripts/db-inspect.sh postgres --thread-id demo-1
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
  uv run mcc-db-inspect "$@"
)
