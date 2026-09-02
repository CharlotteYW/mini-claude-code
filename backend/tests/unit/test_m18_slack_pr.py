"""M18 unit tests: Slack session, OAuth, adapter, open_pull_request."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.channel_session import slack_session_from_event, slack_thread_id
from mini_claude_code.agent.permissions import resolve_permission
from mini_claude_code.agent.slack_adapter import (
    channel_allowed,
    format_agent_reply,
    is_hitl_decision,
    normalize_slack_text,
    run_slack_turn,
    should_ignore_event,
)
from mini_claude_code.agent.slack_oauth import (
    SlackInstallation,
    build_install_url,
    generate_oauth_state,
    load_installations,
    save_installation,
)
from mini_claude_code.config import Settings
from mini_claude_code.tools.github_pr import open_pull_request_impl

pytestmark = pytest.mark.unit


def test_slack_thread_id_stable() -> None:
    tid = slack_thread_id(team_id="T1", channel_id="C1", thread_ts="123.456")
    assert tid == "slack:T1:C1:123.456"


def test_slack_session_from_event_uses_thread_ts() -> None:
    event = {
        "team": "T1",
        "channel": "C1",
        "ts": "100.1",
        "thread_ts": "99.0",
    }
    thread_ts, session_id = slack_session_from_event(event)
    assert thread_ts == "99.0"
    assert session_id == "slack:T1:C1:99.0"


def test_normalize_slack_text_strips_mention() -> None:
    text = normalize_slack_text("<@U123> hello", bot_user_id="U123")
    assert text == "hello"


def test_should_ignore_bot_messages() -> None:
    assert should_ignore_event({"subtype": "bot_message", "text": "x"}, bot_user_id=None)
    assert should_ignore_event({"bot_id": "B1", "text": "x"}, bot_user_id=None)


def test_channel_allowlist() -> None:
    settings = Settings(slack_channel_allowlist="C1,C2")
    assert channel_allowed("C1", settings)
    assert not channel_allowed("C9", settings)
    assert channel_allowed("C9", Settings(slack_channel_allowlist=""))


def test_hitl_decision_words() -> None:
    assert is_hitl_decision("approve")
    assert is_hitl_decision("deny")
    assert not is_hitl_decision("fix the bug")


def test_progress_reaction_helpers() -> None:
    calls: list[tuple[str, str, str]] = []

    class _FakeClient:
        def reactions_add(self, *, channel: str, timestamp: str, name: str) -> None:
            calls.append(("add", channel, name))

        def reactions_remove(self, *, channel: str, timestamp: str, name: str) -> None:
            calls.append(("remove", channel, name))

    from mini_claude_code.agent.slack_bot import SlackProgressIndicator

    client = _FakeClient()
    progress = SlackProgressIndicator(client, emoji="eyes")
    progress.start("C1", "123.456")
    progress.end("C1", "123.456")
    assert calls == [("add", "C1", "eyes"), ("remove", "C1", "eyes")]


def test_oauth_install_url_contains_client_id() -> None:
    url = build_install_url(
        client_id="cid",
        redirect_uri="http://localhost/cb",
        state="abc",
    )
    assert "client_id=cid" in url
    assert "state=abc" in url


def test_installation_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "installs.json"
    inst = SlackInstallation(
        team_id="T1",
        team_name="Team",
        bot_token="xoxb-test",
        bot_user_id="U1",
        installed_at="now",
    )
    save_installation(inst, path)
    loaded = load_installations(path)
    assert loaded["T1"].bot_token == "xoxb-test"


def test_open_pull_request_dry_run(tmp_path: Path) -> None:
    out = open_pull_request_impl(
        "Title",
        "Body",
        workspace_root=tmp_path,
        settings=Settings(pr_dry_run=True),
    )
    data = json.loads(out)
    assert data["dry_run"] is True
    assert data["title"] == "Title"


def test_open_pull_request_plan_mode_denied() -> None:
    assert resolve_permission("open_pull_request", plan_mode=True) == "deny"
    assert resolve_permission("open_pull_request", plan_mode=False) == "ask"


def test_format_agent_reply() -> None:
    text = format_agent_reply(
        [
            HumanMessage(content="hi"),
            AIMessage(content="done"),
        ]
    )
    assert "hi" in text
    assert "done" in text


class _FakeBound:
    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="read ok")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"path": "x.txt"},
                    "id": "r1",
                    "type": "tool_call",
                }
            ],
        )


class _FakeLLM:
    def bind_tools(self, _tools: Any) -> _FakeBound:
        return _FakeBound()


def test_run_slack_turn_help_list_only() -> None:
    event = {
        "team": "T1",
        "channel": "C1",
        "ts": "1.0",
        "user": "U9",
        "text": "/help",
    }
    turn = run_slack_turn(
        event,
        graph=object(),
        settings=Settings(plugins_enabled=False, channel_plan_mode=True),
        plugins=[],
        slash_registry={},
    )
    assert turn is not None
    assert "Slash commands" in turn.reply_text


def test_run_slack_turn_fake_graph_plan_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.agent.graph import build_agent_graph
    from mini_claude_code.config import get_settings
    from mini_claude_code.tools.fs import build_coding_tools

    get_settings.cache_clear()
    (tmp_path / "x.txt").write_text("hello", encoding="utf-8")
    graph = build_agent_graph(
        llm=_FakeLLM(),
        tools=build_coding_tools(tmp_path),
        plan_mode=True,
    )
    event = {
        "team": "T1",
        "channel": "C1",
        "ts": "2.0",
        "user": "U9",
        "text": "read x.txt",
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
    assert turn.exit_code == 0
    assert "read ok" in turn.reply_text.lower() or "hello" in turn.reply_text.lower()
    get_settings.cache_clear()


def test_exchange_oauth_code_parses_response() -> None:
    from mini_claude_code.agent.slack_oauth import SlackInstallation

    payload = {
        "ok": True,
        "access_token": "xoxb-abc",
        "team": {"id": "T1", "name": "Test"},
        "bot_user_id": "U1",
    }
    inst = SlackInstallation.from_oauth_response(payload)
    assert inst.team_id == "T1"
    assert inst.bot_token == "xoxb-abc"


def test_generate_oauth_state_unique() -> None:
    assert generate_oauth_state() != generate_oauth_state()
