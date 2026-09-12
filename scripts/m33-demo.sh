#!/usr/bin/env bash
# M33 demo: structured RouteDecision + forced tool_choice (unit always; live skip OK).
# Usage: ./scripts/m33-demo.sh
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

  echo "==> 1) Unit tests (structured / tool_choice helpers)"
  uv run pytest -m unit tests/unit/test_m33_structured.py -q

  echo
  echo "==> 2) Integration live (skip if provider lacks support)"
  uv run pytest -m integration tests/integration/test_m33_structured_live.py -v

  echo
  echo "==> 3) Library smoke: Pydantic gate + fake structured + forced tool"
  uv run python - <<'PY'
from mini_claude_code.agent.structured import (
    RouteDecision,
    contrast_blurb,
    first_tool_call_name,
    invoke_forced_tool,
    invoke_structured,
    validate_model,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from typing import Any

print(contrast_blurb())
obj = validate_model(
    RouteDecision,
    {"mode": "extract", "reason": "no tools needed", "confidence": 0.9},
)
print("validated:", obj.model_dump())

class FakeSO(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake"
    def _generate(self, messages, stop=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(
            lambda _: schema.model_validate(
                {"mode": "react", "reason": "needs tools", "confidence": 0.55}
            )
        )

print("structured:", invoke_structured(FakeSO(), RouteDecision, "hi").model_dump())

@tool
def add(a: int, b: int) -> int:
    """Add."""
    return a + b

class FakeBind(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-bind"
    def _generate(self, messages, stop=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
    def bind_tools(self, tools, **kwargs):
        name = kwargs.get("tool_choice") or "add"
        return RunnableLambda(
            lambda _m, config=None: AIMessage(
                content="",
                tool_calls=[{
                    "name": name,
                    "args": {"a": 17, "b": 25},
                    "id": "1",
                    "type": "tool_call",
                }],
            )
        )

msg = invoke_forced_tool(FakeBind(), [add], "add", "sum")
print("forced tool:", first_tool_call_name(msg), msg.tool_calls[0]["args"])
PY

  echo
  echo "==> 4) Optional CLI (live; may fail if model lacks structured/tool_choice)"
  echo "    uv run mcc-agent --structured-route 'Summarize text only; no file edits'"
  echo "    uv run mcc-agent --force-tool add 'Compute 17+25 with the add tool'"
)
