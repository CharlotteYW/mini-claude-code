#!/usr/bin/env bash
# One-click interactive chat (multi-turn REPL) — no need to remember uv / --repl.
#
# Usage:
#   ./scripts/chat.sh
#   ./scripts/chat.sh --thread-id my-session
#   ./scripts/chat.sh --plan          # read-mostly (mutating tools denied)
#   ./scripts/chat.sh --sync          # sync runtime shim
#
# Same stack as ./scripts/agent.sh --repl; this just defaults to continuous chat.
# Empty line or Ctrl-D exits. Reuse --thread-id to resume a prior session (Postgres).
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
  # Default to REPL; caller may still pass --thread-id / --plan / etc.
  exec uv run mcc-agent --repl "$@"
)
