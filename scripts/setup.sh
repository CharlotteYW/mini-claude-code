#!/usr/bin/env bash
# Idempotent setup: .env, docker compose, uv sync.
# Does NOT auto-pull gemma4:31b (~20GB). Use: PULL_OLLAMA_MODEL=1 ./scripts/setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> mini-claude-code setup (M0)"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already present"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. Install Docker Desktop / Engine first." >&2
  exit 1
fi

echo "==> Starting docker compose (postgres + neo4j)"
docker compose --env-file .env up -d

echo "==> Waiting for healthy services"
attempts=60
for ((i = 1; i <= attempts; i++)); do
  pg_ok="$(docker inspect --format='{{.State.Health.Status}}' mcc-postgres 2>/dev/null || echo missing)"
  neo_ok="$(docker inspect --format='{{.State.Health.Status}}' mcc-neo4j 2>/dev/null || echo missing)"
  if [[ "$pg_ok" == "healthy" && "$neo_ok" == "healthy" ]]; then
    echo "postgres: healthy, neo4j: healthy"
    break
  fi
  if ((i == attempts)); then
    echo "ERROR: services not healthy in time (postgres=$pg_ok neo4j=$neo_ok)" >&2
    docker compose ps >&2 || true
    exit 1
  fi
  sleep 2
done

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Install: https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "==> uv sync (backend)"
(
  cd "$ROOT/backend"
  uv sync
)

if [[ "${PULL_OLLAMA_MODEL:-}" == "1" ]]; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo "WARNING: PULL_OLLAMA_MODEL=1 but ollama not on PATH; skip pull." >&2
  else
    model="$(grep -E '^LLM_MODEL=' .env | head -1 | cut -d= -f2- || true)"
    model="${model:-gemma4:31b}"
    echo "==> ollama pull ${model} (explicit opt-in)"
    ollama pull "$model"
  fi
else
  echo "==> Skipping ollama pull (default). To pull: PULL_OLLAMA_MODEL=1 ./scripts/setup.sh"
  echo "    Then ensure Ollama is running: ollama serve  # if needed"
fi

echo "==> Ensuring LangGraph Postgres checkpoint tables (idempotent)"
(
  cd backend
  uv run python -c "from mini_claude_code.agent import ensure_postgres_checkpoint_tables; ensure_postgres_checkpoint_tables()"
) || echo "WARNING: checkpoint setup failed (is Compose Postgres up?). Retry after docker compose up." >&2

echo "==> Setup complete. Next: ./scripts/smoke.sh  (agent: ./scripts/agent.sh)"

