#!/usr/bin/env bash
# M34 demo: local JSONL traces + LangSmith status (skip remote without key).
# Usage: ./scripts/m34-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "No .env found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

TRACE_FILE="${TMPDIR:-/tmp}/mcc-m34-demo.jsonl"
rm -f "$TRACE_FILE"

(
  cd "$ROOT/backend"
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a

  echo "==> 1) Unit tests (redact / enrich / JSONL)"
  uv run pytest -m unit tests/unit/test_m34_tracing.py -q

  echo
  echo "==> 2) Integration (local JSONL + optional LangSmith env)"
  uv run pytest -m integration tests/integration/test_m34_tracing_live.py -v

  echo
  echo "==> 3) Library smoke: span tree + JSONL"
  uv run python - <<PY
from pathlib import Path
from mini_claude_code.agent.tracing import (
    JsonlTraceHandler,
    SpanEvent,
    contrast_blurb,
    enrich_run_config,
    span_tree_lines,
    tracing_status,
)

print(contrast_blurb())
print("status:", tracing_status().banner_lines())
print("tree:")
for line in span_tree_lines([
    SpanEvent("run", "run"),
    SpanEvent("llm-1", "llm", parent="run"),
    SpanEvent("add", "tool", parent="llm-1", detail="1+2"),
    SpanEvent("llm-2", "llm", parent="run"),
]):
    print(line)

path = Path("$TRACE_FILE")
h = JsonlTraceHandler(path, run_id="demo")
h.on_chat_model_start({"name": "demo"}, [[]], run_id="l1")
h.on_tool_start({"name": "add"}, "a=1,b=2", run_id="t1", parent_run_id="l1")
h.on_tool_end("3", run_id="t1")
h.on_chat_model_end(None, run_id="l1")
h.close_run(extra={"note": "m34-demo"})
print("wrote", path, "lines=", sum(1 for _ in path.open()))
cfg = enrich_run_config({"configurable": {"thread_id": "demo-t"}}, run_name="demo")
print("metadata", cfg["metadata"])
PY

  echo
  echo "==> 4) Optional CLI with --trace-local (fake-friendly short prompt)"
  echo "    uv run mcc-agent --trace-local $TRACE_FILE --no-stream 'Say hi only'"
)
