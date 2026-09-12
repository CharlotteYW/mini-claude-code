#!/usr/bin/env bash
# M38 demo: remote CI gate unit path + optional live poll.
# Usage: ./scripts/m38-demo.sh
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

  echo "==> 1) Unit tests (poll state machine / wraps / HITL)"
  uv run pytest -m unit tests/unit/test_m38_remote_ci.py -q

  echo
  echo "==> 2) Integration live poll (skip unless M38_LIVE_PR=1 + GH_TOKEN + M38_PR_NUMBER)"
  uv run pytest -m integration tests/integration/test_m38_remote_ci_live.py -v

  echo
  echo "==> 3) Tip"
  echo "    SHIP_REMOTE_CI=1 PR_DRY_RUN=0 GH_TOKEN=... uv run mcc-agent --usage \\"
  echo "      -p 'open a PR then wait_for_checks'"
)
