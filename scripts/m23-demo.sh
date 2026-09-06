#!/usr/bin/env bash
# M23 demo: seed/list plugin packs and show plane merges (no live LLM required).
# Usage: ./scripts/m23-demo.sh
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

  echo "==> 1) Unit tests"
  uv run pytest -m unit tests/unit/test_m23_plugins.py -q

  echo
  echo "==> 2) Integration tests"
  uv run pytest -m integration tests/integration/test_m23_plugins_live.py -q

  echo
  echo "==> 3) Seed workspace plugins + /plugins list"
  uv run python - <<'PY'
from mini_claude_code.agent.plugins import (
    collect_plugin_mcp_connections,
    collect_plugin_skill_defs,
    collect_plugin_subagent_defs,
    resolve_plugins,
)
from mini_claude_code.agent.slash_commands import format_slash_list, slash_registry_from_plugins
from mini_claude_code.config import get_settings, resolve_workspace_root

get_settings.cache_clear()
settings = get_settings()
ws = resolve_workspace_root(settings)
packs = resolve_plugins(settings, workspace_root=ws, seed_examples=True)
print(format_slash_list(slash_registry_from_plugins(packs), plugins=packs))
print("--- merged planes ---")
print("skills:", sorted(collect_plugin_skill_defs(packs)))
print("mcp:", sorted(collect_plugin_mcp_connections(packs)))
print("subagents:", sorted(collect_plugin_subagent_defs(packs)))
PY

  echo
  echo "M23 demo OK."
)
