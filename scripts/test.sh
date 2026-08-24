#!/usr/bin/env bash
# Run pytest using the project uv env (backend/.venv).
# Usage:
#   ./scripts/test.sh
#   ./scripts/test.sh -m unit
#   ./scripts/test.sh -m integration
#   ./scripts/test.sh tests/unit/test_m3_fs_tools.py -v
#   ./scripts/test.sh tests/unit/test_m3_fs_tools.py::test_path_jail_rejects_escape -v
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d backend/.venv ]] && [[ ! -f backend/uv.lock ]]; then
  echo "Backend env missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

(
  cd "$ROOT/backend"
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  fi
  if [[ $# -eq 0 ]]; then
    uv run pytest -m unit -v
  else
    uv run pytest "$@"
  fi
)
