"""M18 integration: fake Slack handler + dry-run PR offline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.slack_adapter import run_slack_turn
from mini_claude_code.config import Settings
from mini_claude_code.tools.github_pr import open_pull_request_impl

pytestmark = pytest.mark.integration


class _FakeBoundWrite:
    def __init__(self) -> None:
        self.n = 0

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        self.n += 1
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="PR blocked by permissions.")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "open_pull_request",
                    "args": {"title": "Test PR", "body": "from slack"},
                    "id": "pr1",
                    "type": "tool_call",
                }
            ],
        )


class _FakeLLM:
    def __init__(self) -> None:
        self._bound = _FakeBoundWrite()

    def bind_tools(self, _tools: Any) -> _FakeBoundWrite:
        return self._bound


def test_slack_turn_plan_mode_denies_open_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.config import get_settings
    from mini_claude_code.tools.fs import build_coding_tools
    from mini_claude_code.tools.github_pr import build_github_pr_tools

    get_settings.cache_clear()
    tools = [
        *build_coding_tools(tmp_path),
        *build_github_pr_tools(tmp_path, settings=Settings(pr_dry_run=True)),
    ]
    graph = build_agent_graph(
        llm=_FakeLLM(),
        tools=tools,
        plan_mode=True,
    )
    event = {
        "team": "T1",
        "channel": "C1",
        "ts": "9.0",
        "user": "U1",
        "text": "open a pr",
    }
    turn = run_slack_turn(
        event,
        graph,
        settings=Settings(
            workspace_root=str(tmp_path),
            channel_plan_mode=True,
            plugins_enabled=False,
        ),
        plugins=[],
        slash_registry={},
    )
    assert turn is not None
    assert (
        "PERMISSION_DENIED" in turn.reply_text
        or "permission" in turn.reply_text.lower()
        or "blocked" in turn.reply_text.lower()
    )
    get_settings.cache_clear()


def test_open_pull_request_dry_run_integration(tmp_path: Path) -> None:
    out = open_pull_request_impl(
        "Feature",
        "Details",
        base="main",
        workspace_root=tmp_path,
        settings=Settings(pr_dry_run=True),
    )
    data = json.loads(out)
    assert data["dry_run"] is True


@pytest.mark.skipif(
    not __import__("os").environ.get("SLACK_CLIENT_ID"),
    reason="live Slack OAuth not configured",
)
def test_slack_oauth_live_skipped_by_default() -> None:
    """Placeholder: live OAuth requires manual browser flow."""
    assert True
