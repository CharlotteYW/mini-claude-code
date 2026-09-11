#!/usr/bin/env bash
# M32 demo: parallel vs serial tool fan-out timing.
# Usage: ./scripts/m32-demo.sh
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

  echo "==> 1) Unit tests (fan-out policy)"
  uv run pytest -m unit tests/unit/test_m32_tool_fanout.py -q

  echo
  echo "==> 2) Integration (fake multi tool_calls through graph)"
  uv run pytest -m integration tests/integration/test_m32_tool_fanout_live.py -v

  echo
  echo "==> 3) Library smoke: wall-clock parallel vs serial"
  uv run python - <<'PY'
import time
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from mini_claude_code.agent.tool_fanout import make_tools_node

@tool("add")
def slow_a() -> str:
    """a"""
    time.sleep(0.25)
    return "a"

@tool("echo")
def slow_b(text: str = "b") -> str:
    """b"""
    time.sleep(0.25)
    return text or "b"

def run(parallel: bool) -> float:
    node = make_tools_node([slow_a, slow_b], parallel=parallel)
    g = StateGraph(MessagesState)
    g.add_node("tools", node)
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    graph = g.compile()
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "add", "args": {}, "id": "1", "type": "tool_call"},
            {"name": "echo", "args": {"text": "b"}, "id": "2", "type": "tool_call"},
        ],
    )
    t0 = time.perf_counter()
    graph.invoke({"messages": [ai]})
    wall = time.perf_counter() - t0
    print(f"  mode={node.last_mode:8s} wall={wall:.3f}s")
    return wall

print("Two 250ms tools:")
wp = run(True)
ws = run(False)
print(f"  speedup ≈ {ws/wp:.2f}x (serial/parallel)")
PY
)
