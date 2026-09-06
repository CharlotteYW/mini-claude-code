#!/usr/bin/env bash
# M24 demo: shell-hooks pack + /pick (no live LLM required).
# Usage: ./scripts/m24-demo.sh
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
  uv run pytest -m unit tests/unit/test_m24_hooks.py -q

  echo
  echo "==> 2) Integration tests"
  uv run pytest -m integration tests/integration/test_m24_hooks_live.py -q

  echo
  echo "==> 3) Shell Pre deny (HOOK_SHELL_ENABLED=1)"
  HOOK_SHELL_ENABLED=1 uv run python - <<'PY'
from pathlib import Path
from mini_claude_code.agent.hooks import resolve_hook_registry, run_pre_hooks
from mini_claude_code.agent.plugins import resolve_plugins
from mini_claude_code.config import Settings

ws = Path("../workspace").resolve()
settings = Settings(
    _env_file=None,
    plugins_enabled=True,
    workspace_root=str(ws),
    hook_shell_enabled=True,
    hooks_use_demo=False,
    hooks_config_path="",
)
resolve_plugins(settings, workspace_root=ws, seed_examples=True)
reg = resolve_hook_registry(settings, workspace_root=ws)
denied = run_pre_hooks(reg, tool="run_shell", args={"command": "echo FORBIDDEN_M24"})
ok = run_pre_hooks(reg, tool="run_shell", args={"command": "echo hi"})
print("denied:", denied.allow, denied.reason)
print("allowed:", ok.allow)
assert denied.allow is False and ok.allow is True
PY

  echo
  echo "==> 4) /pick list (non-interactive)"
  uv run python - <<'PY'
from mini_claude_code.agent.plugins import resolve_plugins
from mini_claude_code.agent.slash_commands import dispatch_slash_input, slash_registry_from_plugins
from mini_claude_code.config import get_settings, resolve_workspace_root

get_settings.cache_clear()
settings = get_settings()
ws = resolve_workspace_root(settings)
packs = resolve_plugins(settings, workspace_root=ws, seed_examples=True)
reg = slash_registry_from_plugins(packs)
d = dispatch_slash_input("/pick", reg, plugins=packs)
print(d.list_text)
PY

  echo
  echo "M24 demo OK. Interactive: HOOK_SHELL_ENABLED=1 mcc-agent /pick"
)
