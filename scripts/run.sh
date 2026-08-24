#!/usr/bin/env bash
# Deprecated alias — use ./scripts/smoke.sh (LLM factory smoke, not the agent).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "NOTE: ./scripts/run.sh is renamed to ./scripts/smoke.sh (agent is ./scripts/agent.sh)" >&2
exec "$ROOT/scripts/smoke.sh" "$@"
