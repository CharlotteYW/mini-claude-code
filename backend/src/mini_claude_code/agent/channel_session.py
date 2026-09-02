"""Map chat-channel threads to checkpointer thread_id strings (M18)."""

from __future__ import annotations


def slack_thread_id(
    *,
    team_id: str,
    channel_id: str,
    thread_ts: str,
) -> str:
    """Stable session key for Slack → LangGraph checkpointer."""
    return f"slack:{team_id}:{channel_id}:{thread_ts}"


def slack_session_from_event(event: dict) -> tuple[str, str]:
    """Return (thread_ts for replies, checkpointer thread_id)."""
    team_id = str(event.get("team") or event.get("team_id") or "")
    channel_id = str(event.get("channel") or "")
    message_ts = str(event.get("ts") or "")
    thread_ts = str(event.get("thread_ts") or message_ts)
    session_id = slack_thread_id(
        team_id=team_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )
    return thread_ts, session_id
