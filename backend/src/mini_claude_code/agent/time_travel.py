"""Time-travel helpers (M31): list checkpoints and fork without rewriting history.

M5 resume always continues from the **tip** of a ``thread_id``.
M31 lists ``checkpoint_id`` history and **forks** a new tip (default: new
``thread_id``) via ``update_state`` copying snapshot values — source tip stays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig


@dataclass(frozen=True)
class CheckpointRow:
    """One row in a teaching-friendly checkpoint listing (newest first)."""

    index: int
    checkpoint_id: str
    thread_id: str
    created_at: str | None
    next_nodes: tuple[str, ...]
    message_count: int
    preview: str


def _checkpoint_id(config: RunnableConfig | None) -> str:
    if not config:
        return ""
    cfg = config.get("configurable") or {}
    return str(cfg.get("checkpoint_id") or "")


def _thread_id(config: RunnableConfig | None) -> str:
    if not config:
        return ""
    cfg = config.get("configurable") or {}
    return str(cfg.get("thread_id") or "")


def _message_preview(values: Any) -> str:
    messages = []
    if isinstance(values, dict):
        messages = list(values.get("messages") or [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            text = str(msg.content).replace("\n", " ").strip()
            return (text[:72] + "…") if len(text) > 72 else text
        content = getattr(msg, "content", None)
        role = getattr(msg, "type", None)
        if role == "human" or (
            isinstance(msg, dict) and msg.get("role") == "user"
        ):
            text = str(content if content is not None else msg).replace("\n", " ")
            text = text.strip()
            return (text[:72] + "…") if len(text) > 72 else text
    return ""


def snapshot_to_row(index: int, snap: Any) -> CheckpointRow:
    values = getattr(snap, "values", {}) or {}
    messages = values.get("messages") if isinstance(values, dict) else None
    count = len(messages) if isinstance(messages, list) else 0
    nxt = tuple(getattr(snap, "next", ()) or ())
    cfg = getattr(snap, "config", None)
    return CheckpointRow(
        index=index,
        checkpoint_id=_checkpoint_id(cfg),
        thread_id=_thread_id(cfg),
        created_at=getattr(snap, "created_at", None),
        next_nodes=nxt,
        message_count=count,
        preview=_message_preview(values),
    )


def format_checkpoint_table(rows: Sequence[CheckpointRow]) -> str:
    if not rows:
        return "No checkpoints for this thread."
    lines = [
        "Checkpoints (newest first). Fork with --fork-from <id|index> or /rewind.",
        "",
        f"{'#':>3}  {'msgs':>4}  {'next':<16}  checkpoint_id",
    ]
    for row in rows:
        nxt = ",".join(row.next_nodes) if row.next_nodes else "(idle)"
        cid = row.checkpoint_id or "(none)"
        lines.append(f"{row.index:>3}  {row.message_count:>4}  {nxt:<16}  {cid}")
        if row.preview:
            lines.append(f"       human: {row.preview}")
        if row.created_at:
            lines.append(f"       at: {row.created_at}")
    return "\n".join(lines)


def resolve_checkpoint_ref(
    rows: Sequence[CheckpointRow], ref: str
) -> CheckpointRow:
    """Resolve 1-based index or checkpoint_id (full or unique prefix)."""
    raw = ref.strip()
    if not raw:
        raise ValueError("empty checkpoint ref")
    if raw.isdigit():
        idx = int(raw)
        for row in rows:
            if row.index == idx:
                return row
        raise ValueError(f"checkpoint index {idx} out of range 1..{len(rows)}")

    exact = [r for r in rows if r.checkpoint_id == raw]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"ambiguous checkpoint id {raw!r}")

    prefix = [r for r in rows if r.checkpoint_id.startswith(raw)]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        raise ValueError(f"ambiguous checkpoint prefix {raw!r}")
    raise ValueError(f"unknown checkpoint ref {raw!r}")


def list_checkpoints(
    graph: Any,
    thread_id: str,
    *,
    limit: int | None = 50,
    completed_only: bool = True,
) -> list[CheckpointRow]:
    """Sync list via ``get_state_history`` (newest first)."""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    rows: list[CheckpointRow] = []
    for snap in graph.get_state_history(config, limit=limit):
        if completed_only and tuple(getattr(snap, "next", ()) or ()):
            continue
        rows.append(snapshot_to_row(len(rows) + 1, snap))
    return rows


async def alist_checkpoints(
    graph: Any,
    thread_id: str,
    *,
    limit: int | None = 50,
    completed_only: bool = True,
) -> list[CheckpointRow]:
    """Async list via ``aget_state_history``."""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    rows: list[CheckpointRow] = []
    async for snap in graph.aget_state_history(config, limit=limit):
        if completed_only and tuple(getattr(snap, "next", ()) or ()):
            continue
        rows.append(snapshot_to_row(len(rows) + 1, snap))
    return rows


def _find_snapshot(
    graph: Any, thread_id: str, checkpoint_id: str
) -> Any:
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    for snap in graph.get_state_history(config):
        cid = _checkpoint_id(getattr(snap, "config", None))
        if cid == checkpoint_id or (
            checkpoint_id and cid.startswith(checkpoint_id)
        ):
            return snap
    raise ValueError(
        f"checkpoint {checkpoint_id!r} not found on thread {thread_id!r}"
    )


async def _afind_snapshot(
    graph: Any, thread_id: str, checkpoint_id: str
) -> Any:
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    async for snap in graph.aget_state_history(config):
        cid = _checkpoint_id(getattr(snap, "config", None))
        if cid == checkpoint_id or (
            checkpoint_id and cid.startswith(checkpoint_id)
        ):
            return snap
    raise ValueError(
        f"checkpoint {checkpoint_id!r} not found on thread {thread_id!r}"
    )


def fork_from_checkpoint(
    graph: Any,
    *,
    source_thread_id: str,
    checkpoint_id: str,
    target_thread_id: str | None = None,
) -> RunnableConfig:
    """Copy snapshot values onto a **new** thread tip (source tip unchanged)."""
    target = (target_thread_id or "").strip() or str(uuid4())
    if target == source_thread_id:
        raise ValueError(
            "target_thread_id must differ from source (fork = new lineage; "
            "same-thread tip rewrite is an anti-pattern in M31)"
        )
    snap = _find_snapshot(graph, source_thread_id, checkpoint_id)
    values = getattr(snap, "values", None)
    if values is None:
        raise ValueError("snapshot has no values to fork")
    return graph.update_state(
        {"configurable": {"thread_id": target}},
        values=values,
    )


async def afork_from_checkpoint(
    graph: Any,
    *,
    source_thread_id: str,
    checkpoint_id: str,
    target_thread_id: str | None = None,
) -> RunnableConfig:
    """Async twin of ``fork_from_checkpoint``."""
    target = (target_thread_id or "").strip() or str(uuid4())
    if target == source_thread_id:
        raise ValueError(
            "target_thread_id must differ from source (fork = new lineage; "
            "same-thread tip rewrite is an anti-pattern in M31)"
        )
    snap = await _afind_snapshot(graph, source_thread_id, checkpoint_id)
    values = getattr(snap, "values", None)
    if values is None:
        raise ValueError("snapshot has no values to fork")
    return await graph.aupdate_state(
        {"configurable": {"thread_id": target}},
        values=values,
    )


def parse_rewind_args(text: str) -> str | None:
    """Return ref after ``/rewind``, or ``None`` if not a rewind command.

    ``/rewind`` alone → empty string (means list).
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    body = stripped[1:].strip()
    if not body:
        return None
    parts = body.split(maxsplit=1)
    if parts[0].lower() != "rewind":
        return None
    return parts[1].strip() if len(parts) > 1 else ""
