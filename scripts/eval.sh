#!/usr/bin/env bash
# Run agent eval cases (M17 fake-LLM harness, no network).
# Usage: ./scripts/eval.sh
#        ./scripts/eval.sh --case backend/evals/cases/tool_path_add.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
uv run mcc-eval "$@"
