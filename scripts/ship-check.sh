#!/usr/bin/env bash
# Local pre-ship gate (M19): ruff + unit tests — same checks as ship_check tool.
# Usage: ./scripts/ship-check.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

echo "==> ruff format --check"
uv run ruff format --check src tests
echo "==> ruff check"
uv run ruff check src tests
echo "==> pytest -m unit"
uv run pytest -m unit -q
echo "ship-check: OK"
