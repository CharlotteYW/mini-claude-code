#!/usr/bin/env bash
# M26 demo: fake_docs MCP content policy (no live LLM required).
# Usage: ./scripts/m26-demo.sh
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

  echo "==> 1) Unit tests (marker detect + client wrap)"
  uv run pytest -m unit tests/unit/test_m26_content_policy.py -q

  echo
  echo "==> 2) Integration: fake_docs stdio deny / allow"
  uv run pytest -m integration tests/integration/test_m26_fake_docs_live.py -q

  echo
  echo "==> 3) Direct read_doc smoke (server-enforced)"
  uv run python - <<'PY'
from mini_claude_code.tools.mcp_loader import fake_docs_connections, load_mcp_tools_sync

tools = {t.name: t for t in load_mcp_tools_sync(fake_docs_connections())}
denied = str(tools["read_doc"].invoke({"doc_id": "secret-no-ai"}))
clean = str(tools["read_doc"].invoke({"doc_id": "clean-guide"}))
assert "CONTENT_POLICY_DENIED" in denied and "SECRET_BODY_M26_ALPHA" not in denied
assert "CONTENT_POLICY_DENIED" not in clean
print("denied:", denied.split("—")[0].strip())
print("clean ok, chars:", len(clean))
print("list_docs:\n", tools["list_docs"].invoke({}))
PY

  echo
  echo "M26 demo OK. Agent path: MCP_USE_FAKE_DOCS=1 mcc-agent ..."
)
