#!/usr/bin/env bash
# M30 demo: LangGraph Store cross-thread KV (no LLM required).
# Usage: ./scripts/m30-demo.sh
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

  echo "==> 1) Unit tests (Store helpers)"
  uv run pytest -m unit tests/unit/test_m30_store.py -q

  echo
  echo "==> 2) Integration Postgres Store (skip if Postgres down)"
  uv run pytest -m integration tests/integration/test_m30_store_live.py -v

  echo
  echo "==> 3) Library smoke: InMemoryStore put then get (two fake thread_ids)"
  uv run python - <<'PY'
from langgraph.store.memory import InMemoryStore

from mini_claude_code.config import Settings
from mini_claude_code.agent.store import store_get_value, store_namespace, store_put_value
from mini_claude_code.tools.memory_tools import build_memory_tools
from pathlib import Path

settings = Settings(_env_file=None, store_project_id="m30-demo")
store = InMemoryStore()
print("namespace:", store_namespace(settings))
print("thread A config would be thread_id=A — Store ignores it")
store_put_value(store, "package_manager", "uv", settings=settings)
print("thread B get:", store_get_value(store, "package_manager", settings=settings))
tools = {t.name: t for t in build_memory_tools(settings, workspace_root=Path("/tmp"), store=store)}
print("tools:", sorted(k for k in tools if k.startswith("store_")))
print(tools["store_get"].invoke({"key": "package_manager"}))
PY
)
