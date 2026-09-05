"""Slack message → agent invoke → reply text (M18).

Pure adapter logic testable without Slack network. Socket Mode wiring lives in slack_bot.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from mini_claude_code.agent.channel_session import slack_session_from_event
from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT
from mini_claude_code.agent.hitl import (
    invoke_with_hitl,
    pending_interrupt_values,
    result_interrupt_values,
)
from mini_claude_code.agent.plugins import PluginPack, resolve_plugins
from mini_claude_code.agent.slash_commands import dispatch_slash_input, slash_registry_from_plugins
from mini_claude_code.config import Settings, get_settings, resolve_workspace_root

_APPROVE_WORDS = frozenset({"approve", "yes", "y"})
_DENY_WORDS = frozenset({"deny", "no", "n"})


@dataclass
class SlackTurnResult:
    reply_text: str
    thread_ts: str
    session_id: str
    exit_code: int = 0


def normalize_slack_text(text: str, *, bot_user_id: str | None = None) -> str:
    """Strip bot mention markup and whitespace."""
    cleaned = text.strip()
    if bot_user_id:
        cleaned = re.sub(rf"<@{re.escape(bot_user_id)}>\s*", "", cleaned).strip()
    return cleaned


def _hitl_decision(text: str) -> bool | None:
    token = text.strip().lower()
    if token in _APPROVE_WORDS:
        return True
    if token in _DENY_WORDS:
        return False
    return None


def is_hitl_decision(text: str) -> bool:
    return _hitl_decision(text) is not None


def channel_allowed(channel_id: str, settings: Settings) -> bool:
    allowlist = settings.slack_channel_allowlist.strip()
    if not allowlist:
        return True
    allowed = {part.strip() for part in allowlist.split(",") if part.strip()}
    return channel_id in allowed


def should_ignore_event(event: dict[str, Any], *, bot_user_id: str | None) -> bool:
    if event.get("subtype") in {"bot_message", "message_changed", "message_deleted"}:
        return True
    if event.get("bot_id"):
        return True
    user = event.get("user")
    if bot_user_id and user == bot_user_id:
        return True
    text = str(event.get("text") or "").strip()
    if not text:
        return True
    return False


def messages_for_this_turn(messages: list[Any]) -> list[Any]:
    """Keep only messages after the latest HumanMessage (this Slack turn).

    Checkpointer returns the full session transcript; Slack already shows prior
    thread posts, so replying with the whole history looks like a bug.
    """
    last_human = -1
    for idx, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_human = idx
    if last_human < 0:
        return list(messages)
    return list(messages[last_human + 1 :])


def format_agent_reply(messages: list[Any], *, this_turn_only: bool = True) -> str:
    """Compact Slack reply — default: this turn's AI/tool output only.

    Skips echoing HumanMessage (already visible in Slack). Prior turns stay in
    the checkpointer for the model, but are not re-posted to the channel.
    """
    view = messages_for_this_turn(messages) if this_turn_only else list(messages)
    lines: list[str] = []
    for message in view:
        if isinstance(message, HumanMessage):
            # User already sees their Slack message; do not echo it.
            continue
        if isinstance(message, ToolMessage):
            preview = str(message.content)
            if len(preview) > 400:
                preview = preview[:400] + "…"
            lines.append(f"Tool[{message.name}]: {preview}")
        elif isinstance(message, AIMessage):
            if message.tool_calls:
                calls = ", ".join(
                    f"{tc.get('name')}({tc.get('args')})" for tc in message.tool_calls
                )
                lines.append(f"AI (tools): {calls}")
            if message.content:
                lines.append(str(message.content))
    if not lines:
        return "(no output)"
    body = "\n".join(lines)
    if len(body) > 3500:
        return body[:3500] + "\n… (truncated)"
    return body


def run_slack_turn(
    event: dict[str, Any],
    graph: Any,
    *,
    settings: Settings | None = None,
    plugins: list[PluginPack] | None = None,
    slash_registry: dict[str, dict[str, str]] | None = None,
    approve_fn: Callable[[Any], bool] | None = None,
) -> SlackTurnResult | None:
    """Process one Slack message event; return reply payload or None if ignored."""
    settings = settings or get_settings()
    bot_user_id = settings.slack_bot_user_id.strip() or None

    if should_ignore_event(event, bot_user_id=bot_user_id):
        return None

    channel_id = str(event.get("channel") or "")
    if not channel_allowed(channel_id, settings):
        return None

    raw_text = str(event.get("text") or "")
    text = normalize_slack_text(raw_text, bot_user_id=bot_user_id)
    if not text:
        return None

    workspace = resolve_workspace_root(settings)
    plugins = plugins if plugins is not None else resolve_plugins(settings, workspace_root=workspace)
    slash_registry = slash_registry or slash_registry_from_plugins(plugins)

    try:
        dispatch = dispatch_slash_input(text, slash_registry, plugins=plugins)
    except ValueError as exc:
        thread_ts, session_id = slack_session_from_event(event)
        return SlackTurnResult(
            reply_text=f"ERROR: {exc}",
            thread_ts=thread_ts,
            session_id=session_id,
            exit_code=1,
        )

    if dispatch.kind == "list":
        thread_ts, session_id = slack_session_from_event(event)
        return SlackTurnResult(
            reply_text=dispatch.list_text,
            thread_ts=thread_ts,
            session_id=session_id,
        )

    thread_ts, session_id = slack_session_from_event(event)
    config: dict = {
        "recursion_limit": DEFAULT_RECURSION_LIMIT,
        "configurable": {"thread_id": session_id},
    }

    plan_mode = bool(settings.channel_plan_mode or settings.agent_plan_mode)

    if not plan_mode and _hitl_decision(text) is not None:
        approved = bool(_hitl_decision(text))
        try:
            result = graph.invoke(Command(resume=approved), config=config)
        except Exception as exc:  # noqa: BLE001
            return SlackTurnResult(
                reply_text=f"ERROR: HITL resume failed: {exc}",
                thread_ts=thread_ts,
                session_id=session_id,
                exit_code=1,
            )
        pending = result_interrupt_values(result) or pending_interrupt_values(
            graph, config
        )
        messages = result.get("messages") or [] if isinstance(result, dict) else []
        reply = format_agent_reply(messages)
        if pending:
            reply += "\n\n(HITL still pending — reply `approve` or `deny`.)"
        return SlackTurnResult(
            reply_text=reply,
            thread_ts=thread_ts,
            session_id=session_id,
        )

    if plan_mode:
        # Plan Mode: no ask interrupts — direct invoke.
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=dispatch.prompt)]},
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            return SlackTurnResult(
                reply_text=f"ERROR: agent run failed: {exc}",
                thread_ts=thread_ts,
                session_id=session_id,
                exit_code=1,
            )
        messages = result.get("messages") or [] if isinstance(result, dict) else []
        return SlackTurnResult(
            reply_text=format_agent_reply(messages),
            thread_ts=thread_ts,
            session_id=session_id,
        )

    def _slack_approve(payload: Any) -> bool:
        if approve_fn is not None:
            return approve_fn(payload)
        return False

    result, code = invoke_with_hitl(
        graph,
        dispatch.prompt,
        config,
        approve_fn=_slack_approve,
    )
    if code != 0 and result is None:
        return SlackTurnResult(
            reply_text="Agent run failed.",
            thread_ts=thread_ts,
            session_id=session_id,
            exit_code=code,
        )
    messages = result.get("messages") or [] if isinstance(result, dict) else []
    reply = format_agent_reply(messages)
    if pending_interrupt_values(graph, config):
        reply += "\n\n(HITL pending — reply `approve` or `deny` in this thread.)"
    return SlackTurnResult(
        reply_text=reply,
        thread_ts=thread_ts,
        session_id=session_id,
        exit_code=code,
    )
