"""LangGraph Store factory (M30): cross-thread KV beside checkpointer.

Checkpointer = per-``thread_id`` transcript.
Store = namespace + key map shared across threads (not a second chat log).
Neo4j Fact / pgvector remain semantic long-term memory.
"""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator, Literal

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from mini_claude_code.config import Settings, get_settings

StoreBackend = Literal["memory", "postgres"]


def resolve_store_backend(
    settings: Settings | None = None,
    *,
    backend: StoreBackend | None = None,
) -> StoreBackend:
    settings = settings or get_settings()
    if backend is not None:
        return backend
    raw = (settings.store_backend or "memory").strip().lower()
    if raw not in ("memory", "postgres"):
        raise ValueError(
            f"STORE_BACKEND must be 'memory' or 'postgres', got {raw!r}"
        )
    return raw  # type: ignore[return-value]


def store_namespace(settings: Settings | None = None) -> tuple[str, ...]:
    """Stable Store namespace — must NOT include ``thread_id``."""
    settings = settings or get_settings()
    project = (settings.store_project_id or "default").strip() or "default"
    return ("mcc", "project", project)


def namespace_prefix(namespace: tuple[str, ...]) -> str:
    """How PostgresStore encodes namespace as ``store.prefix`` (dot-joined)."""
    return ".".join(namespace)


@contextmanager
def open_store(
    settings: Settings | None = None,
    *,
    backend: StoreBackend | None = None,
    setup: bool = True,
) -> Iterator[BaseStore]:
    """Yield a sync Store; Postgres connections stay open for the block."""
    settings = settings or get_settings()
    kind = resolve_store_backend(settings, backend=backend)

    if kind == "memory":
        yield InMemoryStore()
        return

    from langgraph.store.postgres import PostgresStore

    with PostgresStore.from_conn_string(settings.database_url) as store:
        if setup:
            store.setup()
        yield store


@asynccontextmanager
async def open_async_store(
    settings: Settings | None = None,
    *,
    backend: StoreBackend | None = None,
    setup: bool = True,
) -> AsyncIterator[BaseStore]:
    """Yield Store safe for async CLI (``AsyncPostgresStore`` when postgres)."""
    settings = settings or get_settings()
    kind = resolve_store_backend(settings, backend=backend)

    if kind == "memory":
        yield InMemoryStore()
        return

    from langgraph.store.postgres import AsyncPostgresStore

    async with AsyncPostgresStore.from_conn_string(
        settings.database_url
    ) as store:
        if setup:
            await store.setup()
        yield store


def store_put_value(
    store: BaseStore,
    key: str,
    text: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Put a small text value under the project namespace."""
    ns = store_namespace(settings)
    cleaned_key = key.strip()
    if not cleaned_key:
        raise ValueError("store key must be non-empty")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("store value must be non-empty")
    store.put(ns, cleaned_key, {"text": cleaned})


def store_get_value(
    store: BaseStore,
    key: str,
    *,
    settings: Settings | None = None,
) -> str | None:
    """Get text value or None if missing."""
    ns = store_namespace(settings)
    cleaned_key = key.strip()
    if not cleaned_key:
        raise ValueError("store key must be non-empty")
    item = store.get(ns, cleaned_key)
    if item is None:
        return None
    value: Any = item.value
    if isinstance(value, dict) and "text" in value:
        return str(value["text"])
    return str(value)
