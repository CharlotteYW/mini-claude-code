#!/usr/bin/env bash
# M31 demo: list checkpoints + fork (MemorySaver library smoke; Postgres via tests).
# Usage: ./scripts/m31-demo.sh
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

  echo "==> 1) Unit tests (time-travel helpers)"
  uv run pytest -m unit tests/unit/test_m31_time_travel.py -q

  echo
  echo "==> 2) Integration Postgres fork (skip if Postgres down)"
  uv run pytest -m integration tests/integration/test_m31_time_travel_live.py -v

  echo
  echo "==> 3) Library smoke: two turns → list → fork"
  uv run python - <<'PY'
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.time_travel import (
    fork_from_checkpoint,
    format_checkpoint_table,
    list_checkpoints,
)

class Echo:
    def bind_tools(self, _t):
        return self
    def invoke(self, messages, config=None):
        last = messages[-1]
        return AIMessage(content=f"ack:{getattr(last, 'content', last)}")

cp = MemorySaver()
graph = build_agent_graph(
    llm=Echo(), tools=[], checkpointer=cp,
    apply_tool_permissions=False, apply_tool_hooks=False,
)
cfg = {"configurable": {"thread_id": "m31-demo"}, "recursion_limit": 10}
graph.invoke({"messages": [HumanMessage(content="first")]}, cfg)
graph.invoke({"messages": [HumanMessage(content="second-bad")]}, cfg)
rows = list_checkpoints(graph, "m31-demo")
print(format_checkpoint_table(rows))
earlier = min(rows, key=lambda r: r.message_count)
fork = fork_from_checkpoint(
    graph,
    source_thread_id="m31-demo",
    checkpoint_id=earlier.checkpoint_id,
    target_thread_id="m31-demo-fork",
)
print("fork tip msgs", len(graph.get_state(fork).values["messages"]))
print("source tip msgs", len(graph.get_state(cfg).values["messages"]))
PY
)
