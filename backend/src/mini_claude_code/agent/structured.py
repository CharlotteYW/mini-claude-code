"""Structured output & forced tool_choice sidecar (M33).

Default product path stays free-form ReAct (``call_model`` ⇄ PolicyToolNode).
This module teaches two **closed contracts** beside that loop:

1. ``with_structured_output(Pydantic)`` — model reply *is* validated data
   (route / grade / extract), not a tools-node round-trip.
2. ``bind_tools(..., tool_choice=...)`` — API-level “must call this tool”
   (still model-filled args), not prompt hoping.

Contrast (teaching):

| Mode | Contract |
|---|---|
| Free ReAct | May chat or call any bound tool |
| Skills | Prompt playbooks (soft) |
| Subagents | Isolated child context |
| Structured out | Schema-shaped **data** (+ Pydantic gate) |
| Forced tool | Named / required ``tool_calls`` |
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, ValidationError

ControlMode = Literal[
    "react",
    "structured",
    "force_tool",
    "skill",
    "subagent",
]


class RouteDecision(BaseModel):
    """Closed routing decision — structured output demo schema."""

    mode: Literal["react", "extract"]
    reason: str = Field(description="One short reason for the choice.")
    confidence: float = Field(ge=0.0, le=1.0, description="0..1 confidence.")


class GradeResult(BaseModel):
    """Closed grade / judge demo schema (M36 can reuse the idea)."""

    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    rationale: str = Field(description="Brief rationale.")


def contrast_blurb() -> str:
    """Short teaching text for CLI / Learning Log."""
    return (
        "ReAct=flexible tool loop; structured=validated data object; "
        "tool_choice=must emit named tool_call; skills=soft prompt; "
        "subagents=isolated child graph."
    )


def validate_model(schema: type[BaseModel], data: Any) -> BaseModel:
    """Local Pydantic gate (same step LangChain runs after extract)."""
    return schema.model_validate(data)


def normalize_tool_choice(
    tool_choice: str | dict[str, Any] | Literal["auto", "none", "any", "required"],
) -> str | dict[str, Any]:
    """Normalize CLI/env strings into bind_tools ``tool_choice`` values.

    - ``none`` — forbid tools
    - ``any`` / ``required`` — must call some tool
    - other non-empty str — force that **tool name**
    """
    if isinstance(tool_choice, dict):
        return tool_choice
    raw = str(tool_choice).strip()
    if not raw:
        raise ValueError("tool_choice must be non-empty")
    key = raw.lower()
    if key in {"none", "auto"}:
        return key
    if key in {"any", "required"}:
        # LangChain / OpenAI-style: required means must call a tool.
        return "any"
    return raw  # named tool


def bind_with_tool_choice(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    tool_choice: str | dict[str, Any] | Literal["auto", "none", "any", "required"],
) -> Runnable:
    """``bind_tools`` with an explicit ``tool_choice`` (forced / none / any)."""
    choice = normalize_tool_choice(tool_choice)
    return llm.bind_tools(list(tools), tool_choice=choice)


def invoke_structured(
    llm: BaseChatModel,
    schema: type[BaseModel],
    prompt: str | Sequence[BaseMessage],
    **structured_kwargs: Any,
) -> BaseModel:
    """Invoke ``with_structured_output`` and return a validated Pydantic instance.

    Raises whatever the provider / LangChain raises on parse failure
    (typically ``ValidationError`` or provider errors). Retry is caller policy.
    """
    messages: list[BaseMessage] | str
    if isinstance(prompt, str):
        messages = prompt
    else:
        messages = list(prompt)
    runnable = llm.with_structured_output(schema, **structured_kwargs)
    out = runnable.invoke(messages)
    if isinstance(out, BaseModel):
        return out
    # Some paths return dict when schema is not a BaseModel — still gate.
    return schema.model_validate(out)


def invoke_forced_tool(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    tool_choice: str | dict[str, Any] | Literal["auto", "none", "any", "required"],
    prompt: str | Sequence[BaseMessage],
) -> AIMessage:
    """One-shot invoke with forced ``tool_choice``; return the AIMessage."""
    bound = bind_with_tool_choice(llm, tools, tool_choice)
    if isinstance(prompt, str):
        messages: list[BaseMessage] = [HumanMessage(content=prompt)]
    else:
        messages = list(prompt)
    response = bound.invoke(messages)
    if not isinstance(response, AIMessage):
        raise TypeError(f"expected AIMessage, got {type(response)!r}")
    return response


def first_tool_call_name(message: AIMessage) -> str | None:
    """Name of the first tool_call, if any."""
    calls = message.tool_calls or []
    if not calls:
        return None
    call = calls[0]
    if isinstance(call, dict):
        return str(call.get("name") or "") or None
    return str(getattr(call, "name", "") or "") or None


__all__ = [
    "ControlMode",
    "GradeResult",
    "RouteDecision",
    "ValidationError",
    "bind_with_tool_choice",
    "contrast_blurb",
    "first_tool_call_name",
    "invoke_forced_tool",
    "invoke_structured",
    "normalize_tool_choice",
    "validate_model",
]
