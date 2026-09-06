#!/usr/bin/env bash
# M25 demo: install + trust + list (no live LLM).
# Usage: ./scripts/m25-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "No .env found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

DEMO_WS="${ROOT}/workspace/.m25-demo-ws"
rm -rf "$DEMO_WS"
mkdir -p "$DEMO_WS"

(
  cd "$ROOT/backend"
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
  export WORKSPACE_ROOT="$DEMO_WS"
  export PLUGINS_ENABLED=1

  echo "==> 1) Unit + integration"
  uv run pytest -m unit tests/unit/test_m25_plugins_trust.py -q
  uv run pytest -m integration tests/integration/test_m25_plugins_trust_live.py -q

  echo
  echo "==> 2) Install research pack (disabled by default)"
  uv run mcc-plugins install "$ROOT/backend/src/mini_claude_code/agent/plugin_examples/research"

  echo
  echo "==> 3) List (should show research ON=no)"
  uv run mcc-plugins list

  echo
  echo "==> 4) Trust enable"
  uv run mcc-plugins trust research --enable --deny-mcp --deny-shell-hooks
  uv run mcc-plugins list

  echo
  echo "M25 demo OK. Cleanup: rm -rf workspace/.m25-demo-ws"
)
