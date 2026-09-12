"""M33 unit tests: Pydantic gate, tool_choice plumbing, fake structured invoke."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from pydantic import ValidationError

from mini_claude_code.agent.structured import (
    RouteDecision,
    bind_with_tool_choice,
    contrast_blurb,
    first_tool_call_name,
    invoke_forced_tool,
    invoke_structured,
    normalize_tool_choice,
    validate_model,
)

pytestmark = pytest.mark.unit


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool
def echo(text: str) -> str:
    """Echo text."""
    return text


class _FakeStructuredLLM(BaseChatModel):
    """Minimal chat model that implements ``with_structured_output`` for unit tests."""

    payload: dict[str, Any]
    fail_validate: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake-structured-m33"

    def _generate(self, messages: list[Any], stop: Any = None, **kwargs: Any) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="unused"))]
        )

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        payload = dict(self.payload)

        def _run(_input: Any) -> Any:
            if self.fail_validate:
                bad = {"mode": "nope", "reason": "x", "confidence": 9.0}
                return schema.model_validate(bad)
            if isinstance(schema, type):
                return schema.model_validate(payload)
            return payload

        return RunnableLambda(_run)


class _RecordingBindLLM(BaseChatModel):
    """Records ``bind_tools`` tool_choice and returns a matching AIMessage."""

    last_tool_choice: Any = None

    @property
    def _llm_type(self) -> str:
        return "recording-bind-m33"

    def _generate(self, messages: list[Any], stop: Any = None, **kwargs: Any) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="no tools"))]
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        self.last_tool_choice = kwargs.get("tool_choice")
        choice = kwargs.get("tool_choice")
        name = choice if isinstance(choice, str) and choice not in {
            "none",
            "auto",
            "any",
            "required",
        } else (tools[0].name if tools else "add")

        def _invoke(messages: Any, config: Any = None) -> AIMessage:
            if choice == "none":
                return AIMessage(content="chat only")
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": name,
                        "args": {"a": 1, "b": 2} if name == "add" else {"text": "hi"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )

        return RunnableLambda(_invoke)


def test_validate_model_accepts_route_decision() -> None:
    obj = validate_model(
        RouteDecision,
        {"mode": "extract", "reason": "summary", "confidence": 0.7},
    )
    assert isinstance(obj, RouteDecision)
    assert obj.mode == "extract"


def test_validate_model_rejects_bad_payload() -> None:
    with pytest.raises(ValidationError):
        validate_model(
            RouteDecision,
            {"mode": "maybe", "reason": "x", "confidence": 2.0},
        )


def test_normalize_tool_choice() -> None:
    assert normalize_tool_choice("add") == "add"
    assert normalize_tool_choice("none") == "none"
    assert normalize_tool_choice("ANY") == "any"
    assert normalize_tool_choice("required") == "any"
    with pytest.raises(ValueError):
        normalize_tool_choice("  ")


def test_invoke_structured_valid() -> None:
    llm = _FakeStructuredLLM(
        payload={"mode": "react", "reason": "needs tools", "confidence": 0.6}
    )
    out = invoke_structured(llm, RouteDecision, "route please")
    assert out.mode == "react"
    assert out.confidence == 0.6


def test_invoke_structured_validation_error() -> None:
    llm = _FakeStructuredLLM(payload={}, fail_validate=True)
    with pytest.raises(ValidationError):
        invoke_structured(llm, RouteDecision, "route please")


def test_bind_with_tool_choice_records_named() -> None:
    llm = _RecordingBindLLM()
    bound = bind_with_tool_choice(llm, [add, echo], "add")
    assert llm.last_tool_choice == "add"
    msg = bound.invoke([HumanMessage(content="sum")])
    assert isinstance(msg, AIMessage)
    assert first_tool_call_name(msg) == "add"


def test_invoke_forced_tool_helper() -> None:
    llm = _RecordingBindLLM()
    msg = invoke_forced_tool(llm, [add, echo], "add", "compute 1+2")
    assert first_tool_call_name(msg) == "add"


def test_contrast_blurb_mentions_modes() -> None:
    text = contrast_blurb()
    assert "ReAct" in text or "structured" in text
    assert "tool_choice" in text or "subagent" in text
