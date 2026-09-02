"""M17 unit tests: retry, usage, eval cases/assertions."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.retry import invoke_with_retry, is_transient_llm_error
from mini_claude_code.agent.usage import UsageAccumulator
from mini_claude_code.config import Settings
from mini_claude_code.eval.cases import (
    check_assertion,
    load_eval_case,
    EvalAssertion,
)
from mini_claude_code.eval.runner import run_eval_case
from mini_claude_code.eval.cases import EvalCase, FakeStep

pytestmark = pytest.mark.unit


class RateLimitError(Exception):
    pass


def test_is_transient_rate_limit_and_value_error() -> None:
    assert is_transient_llm_error(RateLimitError("slow down"))
    assert is_transient_llm_error(TimeoutError())
    assert not is_transient_llm_error(ValueError("bad prompt"))


def test_invoke_with_retry_succeeds_on_second_attempt() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("retry me")
        return "ok"

    out = invoke_with_retry(
        flaky,
        settings=Settings(llm_max_retries=3, llm_retry_backoff_sec=0),
        sleep=lambda _s: None,
    )
    assert out == "ok"
    assert calls["n"] == 2


def test_invoke_with_retry_gives_up_after_max() -> None:
    with pytest.raises(RateLimitError):
        invoke_with_retry(
            lambda: (_ for _ in ()).throw(RateLimitError("nope")),
            settings=Settings(llm_max_retries=2, llm_retry_backoff_sec=0),
            sleep=lambda _s: None,
        )


def test_invoke_with_retry_does_not_retry_value_error() -> None:
    with pytest.raises(ValueError):
        invoke_with_retry(
            lambda: (_ for _ in ()).throw(ValueError("policy")),
            settings=Settings(llm_max_retries=5, llm_retry_backoff_sec=0),
            sleep=lambda _s: None,
        )


def test_usage_accumulator_metadata_and_fallback() -> None:
    acc = UsageAccumulator()
    acc.record(
        AIMessage(
            content="hi",
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            },
        )
    )
    assert acc.input_tokens == 10
    assert acc.output_tokens == 5
    assert acc.total_tokens == 15
    assert acc.calls_with_metadata == 1

    acc.record(AIMessage(content="no metadata here"))
    assert acc.calls_without_metadata == 1
    assert acc.estimated_fallback_tokens >= 1
    footer = acc.format_footer()
    assert "usage" in footer
    assert "llm_calls" in footer


def test_load_eval_case_valid(tmp_path: Path) -> None:
    path = tmp_path / "case.yaml"
    path.write_text(
        """
name: demo
prompt: hello
fake_llm:
  steps:
    - content: ok
assertions:
  - type: content_contains
    text: ok
""",
        encoding="utf-8",
    )
    case = load_eval_case(path)
    assert case.name == "demo"
    assert case.prompt == "hello"
    assert len(case.fake_steps) == 1


def test_load_eval_case_missing_name(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("prompt: only\n", encoding="utf-8")
    with pytest.raises(ValueError, match="name"):
        load_eval_case(path)


def test_assertions_on_transcript() -> None:
    messages = [
        HumanMessage(content="go"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "add",
                    "args": {"a": 1, "b": 2},
                    "id": "1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="3", tool_call_id="1", name="add"),
        AIMessage(content="answer is 3"),
    ]
    check_assertion(EvalAssertion(type="tool_called", name="add"), messages)
    check_assertion(EvalAssertion(type="content_contains", text="3"), messages)


def test_permission_denied_assertion() -> None:
    messages = [
        ToolMessage(content="PERMISSION_DENIED: Plan Mode", tool_call_id="x", name="write_file"),
    ]
    check_assertion(EvalAssertion(type="permission_denied"), messages)


def test_unknown_assertion_type() -> None:
    with pytest.raises(ValueError, match="unknown"):
        check_assertion(EvalAssertion(type="magic"), [])


def test_run_eval_case_tool_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()
    case = EvalCase(
        name="inline_add",
        prompt="add",
        toolset="demo",
        fake_steps=[
            FakeStep(
                tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "c1"}]
            ),
            FakeStep(content="sum is 5"),
        ],
        assertions=[
            EvalAssertion(type="tool_called", name="add"),
            EvalAssertion(type="content_contains", text="5"),
        ],
    )
    result = run_eval_case(case, workspace=tmp_path)
    assert result.passed
    get_settings.cache_clear()
