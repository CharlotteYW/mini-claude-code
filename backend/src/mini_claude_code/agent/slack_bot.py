"""Slack Socket Mode bot wiring (M18)."""

from __future__ import annotations

import sys
from typing import Any, Callable

from mini_claude_code.agent.checkpointer import CheckpointBackend, open_checkpointer
from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.slack_adapter import (
    SlackTurnResult,
    channel_allowed,
    normalize_slack_text,
    run_slack_turn,
    should_ignore_event,
)
from mini_claude_code.agent.slack_oauth import resolve_bot_token
from mini_claude_code.config import Settings, get_settings


def post_slack_reply(
    client: Any,
    *,
    channel: str,
    thread_ts: str,
    text: str,
) -> None:
    client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)


def add_message_reaction(
    client: Any,
    *,
    channel: str,
    timestamp: str,
    name: str,
) -> None:
    """Best-effort 👀 / hourglass on the user's message while the agent runs."""
    if not channel or not timestamp or not name:
        return
    try:
        client.reactions_add(channel=channel, timestamp=timestamp, name=name)
    except Exception as exc:  # noqa: BLE001
        print(f"[slack] reactions.add failed ({name}): {exc}", file=sys.stderr)


def remove_message_reaction(
    client: Any,
    *,
    channel: str,
    timestamp: str,
    name: str,
) -> None:
    if not channel or not timestamp or not name:
        return
    try:
        client.reactions_remove(channel=channel, timestamp=timestamp, name=name)
    except Exception as exc:  # noqa: BLE001
        print(f"[slack] reactions.remove failed ({name}): {exc}", file=sys.stderr)


class SlackProgressIndicator:
    """Add/remove a progress emoji on the triggering message."""

    def __init__(self, client: Any, *, emoji: str) -> None:
        self._client = client
        self._emoji = emoji.strip(":")

    def start(self, channel: str, message_ts: str) -> None:
        add_message_reaction(
            self._client,
            channel=channel,
            timestamp=message_ts,
            name=self._emoji,
        )

    def end(self, channel: str, message_ts: str) -> None:
        remove_message_reaction(
            self._client,
            channel=channel,
            timestamp=message_ts,
            name=self._emoji,
        )


def handle_slack_message_event(
    event: dict[str, Any],
    graph: Any,
    *,
    settings: Settings | None = None,
    post_reply: Callable[[str, str, str], None] | None = None,
    progress: SlackProgressIndicator | None = None,
) -> SlackTurnResult | None:
    """Adapter + optional Slack post. ``post_reply(channel, thread_ts, text)`` when set."""
    settings = settings or get_settings()
    bot_user_id = settings.slack_bot_user_id.strip() or None
    if should_ignore_event(event, bot_user_id=bot_user_id):
        return None
    channel = str(event.get("channel") or "")
    if not channel_allowed(channel, settings):
        return None
    text = normalize_slack_text(str(event.get("text") or ""), bot_user_id=bot_user_id)
    if not text:
        return None

    message_ts = str(event.get("ts") or "")
    if progress is not None:
        progress.start(channel, message_ts)
    try:
        turn = run_slack_turn(event, graph, settings=settings)
        if turn is None:
            return None
        if post_reply is not None:
            post_reply(channel, turn.thread_ts, turn.reply_text)
        return turn
    finally:
        if progress is not None:
            progress.end(channel, message_ts)


def build_channel_graph(settings: Settings | None = None, checkpointer: Any = None):
    settings = settings or get_settings()
    plan_mode = bool(settings.channel_plan_mode or settings.agent_plan_mode)
    return build_agent_graph(
        settings=settings,
        checkpointer=checkpointer,
        plan_mode=plan_mode,
        ask_callback=None,
    )


def run_socket_mode_bot(
    *,
    settings: Settings | None = None,
    team_id: str | None = None,
    checkpointer_backend: CheckpointBackend | None = None,
) -> None:
    """Long-running Slack Socket Mode listener."""
    settings = settings or get_settings()
    app_token = settings.slack_app_token.strip()
    if not app_token:
        raise ValueError("SLACK_APP_TOKEN is required for Socket Mode")

    bot_token = resolve_bot_token(team_id, settings=settings)
    if not bot_token:
        raise ValueError(
            "No bot token — run `mcc-slack install` or set SLACK_BOT_TOKEN"
        )

    try:
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.request import SocketModeRequest
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.web import WebClient
    except ImportError as exc:
        raise ImportError(
            "slack-sdk is required — install with uv sync in backend/"
        ) from exc

    web = WebClient(token=bot_token)
    socket = SocketModeClient(app_token=app_token, web_client=web)
    progress = SlackProgressIndicator(web, emoji=settings.slack_progress_emoji)

    with open_checkpointer(
        settings, backend=checkpointer_backend, setup=True
    ) as checkpointer:
        graph = build_channel_graph(settings, checkpointer=checkpointer)

        def _process(client: SocketModeClient, req: SocketModeRequest) -> None:
            if req.type != "events_api":
                return
            client.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id)
            )
            payload = req.payload or {}
            event = payload.get("event") or {}
            if event.get("type") != "message":
                return

            def _post(channel: str, thread_ts: str, text: str) -> None:
                post_slack_reply(web, channel=channel, thread_ts=thread_ts, text=text)

            handle_slack_message_event(
                event,
                graph,
                settings=settings,
                post_reply=_post,
                progress=progress,
            )

        socket.socket_mode_request_listeners.append(_process)
        socket.connect()
        emoji = settings.slack_progress_emoji.strip(":") or "eyes"
        print(
            f"Slack Socket Mode bot connected "
            f"(progress reaction :{emoji}:). Press Ctrl+C to stop."
        )
        from threading import Event

        try:
            Event().wait()
        finally:
            socket.disconnect()
