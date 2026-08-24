"""Checkpointer factory (M5): MemorySaver vs Postgres.

Same StateGraph API; durability differs:
- MemorySaver: process RAM only (unit tests / offline demos)
- PostgresSaver: survives process restart (real sessions)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.config import Settings, get_settings

CheckpointBackend = Literal["memory", "postgres"]


def resolve_checkpoint_backend(
    settings: Settings | None = None,
    *,
    backend: CheckpointBackend | None = None,
) -> CheckpointBackend:
    settings = settings or get_settings()
    if backend is not None:
        return backend
    raw = (settings.checkpoint_backend or "postgres").strip().lower()
    if raw not in ("memory", "postgres"):
        raise ValueError(
            f"CHECKPOINT_BACKEND must be 'memory' or 'postgres', got {raw!r}"
        )
    return raw  # type: ignore[return-value]


@contextmanager
def open_checkpointer(
    settings: Settings | None = None,
    *,
    backend: CheckpointBackend | None = None,
    setup: bool = True,
) -> Iterator[BaseCheckpointSaver]:
    """Yield a checkpointer; Postgres connections stay open for the block.

    Call `setup=True` once (idempotent) so checkpoint tables exist.
    """
    settings = settings or get_settings()
    kind = resolve_checkpoint_backend(settings, backend=backend)

    if kind == "memory":
        yield MemorySaver()
        return

    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        if setup:
            checkpointer.setup()
        yield checkpointer


def ensure_postgres_checkpoint_tables(settings: Settings | None = None) -> None:
    """Idempotent schema setup for Compose/bootstrap scripts."""
    settings = settings or get_settings()
    with open_checkpointer(settings, backend="postgres", setup=True):
        pass
