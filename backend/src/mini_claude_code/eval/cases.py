"""YAML eval case loading and assertion helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


@dataclass
class FakeStep:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvalAssertion:
    type: str
    text: str | None = None
    name: str | None = None


@dataclass
class EvalCase:
    name: str
    prompt: str
    toolset: str = "demo"
    plan_mode: bool = False
    live: bool = False
    fake_steps: list[FakeStep] = field(default_factory=list)
    assertions: list[EvalAssertion] = field(default_factory=list)
    description: str = ""


def _parse_step(raw: dict[str, Any]) -> FakeStep:
    tool_calls = raw.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        raise ValueError("tool_calls must be a list")
    return FakeStep(content=str(raw.get("content") or ""), tool_calls=tool_calls)


def _parse_assertion(raw: dict[str, Any]) -> EvalAssertion:
    atype = raw.get("type")
    if not atype:
        raise ValueError("assertion missing type")
    return EvalAssertion(
        type=str(atype),
        text=raw.get("text"),
        name=raw.get("name"),
    )


def load_eval_case(path: Path) -> EvalCase:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    name = data.get("name")
    prompt = data.get("prompt")
    if not name or not prompt:
        raise ValueError(f"{path}: requires name and prompt")
    fake_raw = data.get("fake_llm") or {}
    steps_raw = fake_raw.get("steps") if isinstance(fake_raw, dict) else None
    steps: list[FakeStep] = []
    if steps_raw:
        if not isinstance(steps_raw, list):
            raise ValueError("fake_llm.steps must be a list")
        steps = [_parse_step(s) for s in steps_raw]
    assertions_raw = data.get("assertions") or []
    if not isinstance(assertions_raw, list):
        raise ValueError("assertions must be a list")
    assertions = [_parse_assertion(a) for a in assertions_raw]
    return EvalCase(
        name=str(name),
        description=str(data.get("description") or ""),
        prompt=str(prompt),
        toolset=str(data.get("toolset") or "demo"),
        plan_mode=bool(data.get("plan_mode", False)),
        live=bool(data.get("live", False)),
        fake_steps=steps,
        assertions=assertions,
    )


def transcript_text(messages: list[BaseMessage]) -> str:
    parts: list[str] = []
    for message in messages:
        parts.append(str(message.content))
        if isinstance(message, AIMessage) and message.tool_calls:
            parts.append(str(message.tool_calls))
        if isinstance(message, ToolMessage):
            parts.append(message.name or "")
    return "\n".join(parts)


def check_assertion(
    assertion: EvalAssertion,
    messages: list[BaseMessage],
) -> None:
    text = transcript_text(messages)
    if assertion.type == "content_contains":
        if not assertion.text:
            raise ValueError("content_contains requires text")
        if assertion.text not in text:
            raise AssertionError(
                f"content_contains: {assertion.text!r} not in transcript"
            )
        return
    if assertion.type == "tool_called":
        if not assertion.name:
            raise ValueError("tool_called requires name")
        for message in messages:
            if isinstance(message, AIMessage):
                for tc in message.tool_calls or []:
                    if tc.get("name") == assertion.name:
                        return
            if isinstance(message, ToolMessage) and message.name == assertion.name:
                return
        raise AssertionError(f"tool_called: {assertion.name!r} not found")
    if assertion.type == "permission_denied":
        if "PERMISSION_DENIED" not in text:
            raise AssertionError("permission_denied: PERMISSION_DENIED not in transcript")
        return
    raise ValueError(f"unknown assertion type: {assertion.type!r}")
