"""M37 unit tests: budget trigger, prompt-cache markers, usage cache footer."""

from __future__ import annotations

from typing import Any, Sequence

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from mini_claude_code.agent.compact import (
    effective_compact_threshold,
    estimate_tokens,
    maybe_compact_messages,
)
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.prompt_cache import (
    invoke_kwargs_for_prompt_cache,
    mark_stable_prefix_for_cache,
    supports_prompt_cache,
)
from mini_claude_code.agent.usage import UsageAccumulator, extract_cache_tokens
from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.unit


def test_effective_compact_threshold_precedence() -> None:
    assert effective_compact_threshold(0, 0) == 0
    assert effective_compact_threshold(6000, 0) == 6000
    assert effective_compact_threshold(0, 2000) == 2000
    assert effective_compact_threshold(6000, 2000) == 2000
    assert effective_compact_threshold(1000, 5000) == 1000


def test_soft_budget_triggers_compact() -> None:
    calls: list[int] = []

    def summarizer(prefix: Sequence[BaseMessage]) -> BaseMessage:
        calls.append(len(prefix))
        return SystemMessage(content="[conversation summary]\nok")

    messages = [
        HumanMessage(content=("goal " * 200).strip()),
        AIMessage(content=("ack " * 200).strip()),
        HumanMessage(content="recent"),
        AIMessage(content="tail"),
    ]
    assert estimate_tokens(messages) > 50
    # Legacy threshold high; soft budget low → still compact.
    trigger = effective_compact_threshold(10_000, 50)
    out, did = maybe_compact_messages(
        messages,
        threshold_tokens=trigger,
        keep_recent=2,
        summarizer=summarizer,
    )
    assert did is True
    assert calls
    assert estimate_tokens(out) < estimate_tokens(messages)


def test_under_budget_no_compact() -> None:
    calls: list[int] = []

    def summarizer(prefix: Sequence[BaseMessage]) -> BaseMessage:
        calls.append(len(prefix))
        return SystemMessage(content="nope")

    messages = [HumanMessage(content="hi"), AIMessage(content="yo")]
    trigger = effective_compact_threshold(10_000, 5_000)
    out, did = maybe_compact_messages(
        messages,
        threshold_tokens=trigger,
        keep_recent=4,
        summarizer=summarizer,
    )
    assert did is False
    assert out == messages
    assert calls == []


def test_prompt_cache_anthropic_marks_leading_system() -> None:
    assert supports_prompt_cache("anthropic")
    assert not supports_prompt_cache("ollama")
    msgs = [
        SystemMessage(content="AGENT.md rules"),
        SystemMessage(content="skills catalog"),
        HumanMessage(content="hello"),
    ]
    marked = mark_stable_prefix_for_cache(
        msgs, provider="anthropic", enabled=True
    )
    assert isinstance(marked[1].content, list)
    last_block = marked[1].content[-1]
    assert isinstance(last_block, dict)
    assert last_block.get("cache_control") == {"type": "ephemeral"}
    assert marked[2].content == "hello"

    noop = mark_stable_prefix_for_cache(msgs, provider="ollama", enabled=True)
    assert noop[0].content == "AGENT.md rules"
    assert invoke_kwargs_for_prompt_cache("anthropic") == {
        "cache_control": {"type": "ephemeral"}
    }
    assert invoke_kwargs_for_prompt_cache("openai") == {}
    assert invoke_kwargs_for_prompt_cache("anthropic", enabled=False) == {}


def test_usage_footer_cache_and_budget() -> None:
    assert extract_cache_tokens(
        {"input_token_details": {"cache_read": 100, "cache_creation": 40}}
    ) == (100, 40)
    assert extract_cache_tokens({"cache_read_input_tokens": 7}) == (7, 0)

    acc = UsageAccumulator()
    acc.note_prompt_stats(
        prompt_estimate=1200, soft_budget=2000, effective_compact_at=2000
    )
    acc.record(
        AIMessage(
            content="ok",
            usage_metadata={
                "input_tokens": 50,
                "output_tokens": 10,
                "total_tokens": 60,
                "input_token_details": {
                    "cache_read": 30,
                    "cache_creation": 20,
                },
            },
        )
    )
    assert acc.cache_read_tokens == 30
    assert acc.cache_creation_tokens == 20
    footer = acc.format_footer()
    assert "cache_read_tokens" in footer
    assert "prompt_estimate" in footer
    assert "soft_budget" in footer


def test_graph_passes_cache_kwargs_for_anthropic(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mini_claude_code.agent.graph.recall_facts_block",
        lambda **kwargs: "",
    )
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="test-key",
        CONTEXT_COMPACT_THRESHOLD=0,
        CONTEXT_TOKEN_BUDGET=0,
        PROMPT_CACHE_ENABLED=True,
        WORKSPACE_ROOT=str(tmp_path),
        PLUGINS_ENABLED=False,
        HOOKS_USE_DEMO=False,
        MCP_USE_DEMO=False,
    )
    get_settings.cache_clear()
    captured: dict[str, Any] = {}

    class _Bound:
        def invoke(self, messages: Any, config: Any = None, **kwargs: Any) -> AIMessage:
            captured["kwargs"] = kwargs
            captured["messages"] = messages
            return AIMessage(content="cached-ok")

    class _Model:
        def bind_tools(self, tools: Any) -> _Bound:
            return _Bound()

    graph = build_agent_graph(
        settings=settings,
        llm=_Model(),  # type: ignore[arg-type]
        tools=[],
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    (tmp_path / "AGENT.md").write_text("# agent\nrules\n", encoding="utf-8")
    result = graph.invoke(
        {"messages": [HumanMessage(content="hi")]},
        {"configurable": {"thread_id": "m37"}},
    )
    assert captured["kwargs"].get("cache_control") == {"type": "ephemeral"}
    # Last leading SystemMessage (stable prefix) should carry cache_control.
    leading_sys: list[SystemMessage] = []
    for m in captured["messages"]:
        if isinstance(m, SystemMessage):
            leading_sys.append(m)
            continue
        break
    assert leading_sys
    content = leading_sys[-1].content
    assert isinstance(content, list)
    assert content[-1].get("cache_control") == {"type": "ephemeral"}
    assert "cached-ok" in str(result["messages"][-1].content)
