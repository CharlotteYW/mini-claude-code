"""M30 integration: PostgresStore put survives a new client (skip if Postgres down)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.agent.store import (
    open_store,
    store_get_value,
    store_put_value,
)

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _postgres_or_skip(settings: Settings) -> None:
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")


def test_postgres_store_put_get_across_clients() -> None:
    base = _load_repo_settings()
    _postgres_or_skip(base)
    project = f"m30-{uuid4().hex[:8]}"
    settings = base.model_copy(update={"store_project_id": project})
    key = f"pref-{uuid4().hex[:6]}"
    value = "cross-process-ok"

    with open_store(settings, backend="postgres", setup=True) as store_a:
        store_put_value(store_a, key, value, settings=settings)
        assert store_get_value(store_a, key, settings=settings) == value

    # New client / connection — same DB table, same namespace.
    with open_store(settings, backend="postgres", setup=True) as store_b:
        assert store_get_value(store_b, key, settings=settings) == value
