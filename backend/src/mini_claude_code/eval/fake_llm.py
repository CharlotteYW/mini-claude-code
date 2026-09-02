"""Scripted fake LLM for eval cases."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from mini_claude_code.eval.cases import FakeStep


def step_to_ai_message(step: FakeStep) -> AIMessage:
    if step.tool_calls:
        calls: list[dict[str, Any]] = []
        for idx, raw in enumerate(step.tool_calls):
            calls.append(
                {
                    "name": raw["name"],
                    "args": dict(raw.get("args") or {}),
                    "id": raw.get("id") or f"eval-{idx}",
                    "type": "tool_call",
                }
            )
        return AIMessage(content=step.content or "", tool_calls=calls)
    return AIMessage(content=step.content or "(empty scripted reply)")


class ScriptedBound:
    def __init__(self, steps: list[FakeStep]) -> None:
        self._steps = list(steps)
        self._index = 0

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        if self._index >= len(self._steps):
            return AIMessage(content="(script exhausted)")
        step = self._steps[self._index]
        self._index += 1
        return step_to_ai_message(step)


class ScriptedFakeLLM:
    """Minimal fake chat model: ``bind_tools`` returns scripted ``invoke`` steps."""

    def __init__(self, steps: list[FakeStep]) -> None:
        self._steps = steps

    def bind_tools(self, _tools: Any) -> ScriptedBound:
        return ScriptedBound(self._steps)
