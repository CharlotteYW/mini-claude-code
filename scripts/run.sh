#!/usr/bin/env bash
# Smoke demo: print provider/model and construct LangChain chat client.
# Optional: ./scripts/run.sh --ping
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "No .env found. Run ./scripts/setup.sh first (or cp .env.example .env)." >&2
  exit 1
fi

if [[ ! -d backend/.venv ]] && [[ ! -f backend/uv.lock ]]; then
  echo "Backend env missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

echo "==> docker compose status"
docker compose --env-file .env ps || true

echo "==> LLM factory smoke"
(
  cd "$ROOT/backend"
  # Load repo-root .env into the process for pydantic-settings / dotenv.
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
  uv run mcc-smoke "$@"
)
