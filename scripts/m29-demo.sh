#!/usr/bin/env bash
# M29 demo: Streamable HTTP MCP + sticky session (no LLM required).
# Usage: ./scripts/m29-demo.sh
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

  echo "==> 1) Unit tests (HTTP parse + sticky mock)"
  uv run pytest -m unit tests/unit/test_m29_mcp_http.py -q

  echo
  echo "==> 2) Integration (spawns http_counter; skip only if bind fails hard)"
  uv run pytest -m integration tests/integration/test_m29_mcp_http_live.py -v

  echo
  echo "==> 3) Library smoke: sticky bumps accumulate"
  uv run python - <<'PY'
from mini_claude_code.tools.mcp_http_demo import start_http_counter_server
from mini_claude_code.tools.mcp_loader import load_mcp_tools_sync
from mini_claude_code.tools.mcp_sticky import reset_sticky_http_runtime_for_tests

reset_sticky_http_runtime_for_tests()
server = start_http_counter_server()
try:
    tools = {t.name: t for t in load_mcp_tools_sync({"http_counter": server.connection()})}
    print("tools:", sorted(tools))
    print("bump1:", tools["bump_counter"].invoke({"delta": 1}))
    print("bump2:", tools["bump_counter"].invoke({"delta": 2}))
    print("get:", tools["get_counter"].invoke({}))
finally:
    reset_sticky_http_runtime_for_tests()
    server.stop()
    print("(server stopped)")
PY
)
