"""M34 unit tests: redaction, config enrichment, span tree, JSONL handler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from mini_claude_code.agent.tracing import (
    JsonlTraceHandler,
    SpanEvent,
    enrich_run_config,
    redact_secrets,
    redact_value,
    span_tree_lines,
    tracing_status,
)
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


def test_redact_secrets_api_key_and_sk() -> None:
    raw = "Authorization: Bearer tok_abc123 and sk-abcdefghijklmnopqrstuvwxyz"
    out = redact_secrets(raw)
    assert "tok_abc123" not in out or "[REDACTED]" in out
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in out
    assert "[REDACTED]" in out


def test_redact_value_nested() -> None:
    data = {"ok": "hello", "nested": {"api_key": "secret-value-here"}}
    out = redact_value(data)
    assert out["ok"] == "hello"
    assert "[REDACTED]" in str(out["nested"]["api_key"])


def test_enrich_run_config_metadata_and_tags() -> None:
    settings = Settings(llm_provider="ollama", llm_model="test-model")
    cfg = enrich_run_config(
        {"recursion_limit": 10, "configurable": {"thread_id": "t-1"}},
        settings=settings,
        run_name="unit-run",
        extra_tags=["unit"],
        extra_metadata={"api_key": "sk-should-redact-please"},
    )
    assert cfg["run_name"] == "unit-run"
    assert "mini-claude-code" in cfg["tags"]
    assert "unit" in cfg["tags"]
    assert cfg["metadata"]["thread_id"] == "t-1"
    assert cfg["metadata"]["llm_provider"] == "ollama"
    assert "sk-should-redact-please" not in str(cfg["metadata"])


def test_span_tree_lines_hierarchy() -> None:
    events = [
        SpanEvent(name="run", kind="run"),
        SpanEvent(name="llm-1", kind="llm", parent="run"),
        SpanEvent(name="add", kind="tool", parent="llm-1", detail="tool"),
        SpanEvent(name="llm-2", kind="llm", parent="run"),
    ]
    lines = span_tree_lines(events)
    text = "\n".join(lines)
    assert "[run] run" in text
    assert "[llm] llm-1" in text
    assert "[tool] add" in text
    assert lines[0].startswith("- ")
    assert any(line.startswith("  - ") for line in lines)


def test_jsonl_trace_handler_writes_events(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    handler = JsonlTraceHandler(path, run_id="r1")
    handler.on_chat_model_start(
        {"name": "FakeLLM"},
        [[HumanMessage(content="hi")]],
        run_id="s1",
        parent_run_id=None,
    )
    handler.on_chat_model_end(AIMessage(content="ok"), run_id="s1")
    handler.on_tool_start(
        {"name": "add"},
        "a=1",
        run_id="s2",
        parent_run_id="s1",
    )
    handler.on_tool_end("42", run_id="s2")
    handler.close_run(status="ok", extra={"thread_id": "t"})

    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    kinds = [r["event"] for r in rows]
    assert kinds[0] == "run_start"
    assert "llm_start" in kinds
    assert "tool_start" in kinds
    assert kinds[-1] == "run_end"
    assert rows[-1]["extra"]["thread_id"] == "t"


def test_tracing_status_banner_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    status = tracing_status()
    assert not status.langsmith_active
    assert any("off" in line for line in status.banner_lines())
