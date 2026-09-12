#!/usr/bin/env bash
# M35 demo: supervisor↔specialist handoff (fake LLM in library smoke).
# Usage: ./scripts/m35-demo.sh
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

  echo "==> 1) Unit tests (handoff transitions / isolation / graph)"
  uv run pytest -m unit tests/unit/test_m35_handoff.py -q

  echo
  echo "==> 2) Integration fake two-step handoff"
  uv run pytest -m integration tests/integration/test_m35_handoff_live.py -v

  echo
  echo "==> 3) Library smoke"
  uv run python - <<'PY'
from langchain_core.messages import AIMessage
from mini_claude_code.agent.handoff import contrast_blurb, run_handoff_demo

print(contrast_blurb())

class Scripted:
    def __init__(self):
        self.i = 0
        self.resps = [
            AIMessage(content="", tool_calls=[{
                "name": "handoff_to",
                "args": {"agent": "researcher", "reason": "facts", "note": "n=1"},
                "id": "a", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "handoff_to",
                "args": {"agent": "supervisor", "reason": "back"},
                "id": "b", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "finish",
                "args": {"summary": "ok"},
                "id": "c", "type": "tool_call",
            }]),
        ]
    def bind_tools(self, _t):
        return self
    def invoke(self, _m, config=None):
        r = self.resps[self.i]
        self.i += 1
        return r

out = run_handoff_demo(Scripted(), "demo task")
print("status", out["status"], "handoffs", out["handoff_count"], "pad", out["scratchpad"])
PY

  echo
  echo "==> 4) Optional live CLI"
  echo "    uv run mcc-agent --handoff-demo 'Research then draft a one-line summary of LangGraph handoff'"
)
