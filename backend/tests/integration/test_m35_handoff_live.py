"""M35 integration: fake-LLM two-step handoff (no network)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from mini_claude_code.agent.handoff import contrast_blurb, run_handoff_demo

pytestmark = pytest.mark.integration


class _ScriptedLLM:
    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self._i = 0

    def bind_tools(self, _tools: Any) -> Any:
        return self

    def invoke(self, _messages: Any, config: Any = None) -> AIMessage:
        if self._i >= len(self._responses):
            return AIMessage(content="done talking")
        msg = self._responses[self._i]
        self._i += 1
        return msg


def test_two_step_handoff_supervisor_researcher_finish() -> None:
    assert "run_subagent" in contrast_blurb() or "M12" in contrast_blurb()
    llm = _ScriptedLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "handoff_to",
                        "args": {
                            "agent": "writer",
                            "reason": "draft please",
                            "note": "tone=short",
                        },
                        "id": "1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "handoff_to",
                        "args": {"agent": "supervisor", "reason": "draft ready"},
                        "id": "2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish",
                        "args": {"summary": "shipped draft"},
                        "id": "3",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    )
    out = run_handoff_demo(llm, "Write a one-line blurb", max_handoffs=4)
    assert out["status"] == "done"
    assert out["handoff_count"] == 2
    assert "tone=short" in out["scratchpad"]
