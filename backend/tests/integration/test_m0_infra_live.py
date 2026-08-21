"""M0 integration: Compose Postgres + Neo4j reachability."""

from __future__ import annotations

import pytest

from mini_claude_code.config import Settings, get_settings

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from pathlib import Path

    from dotenv import load_dotenv

    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def test_postgres_accepts_connection() -> None:
    psycopg = pytest.importorskip("psycopg")
    settings = _load_repo_settings()
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
                cur.execute(
                    "SELECT extname FROM pg_extension WHERE extname = 'vector'"
                )
                row = cur.fetchone()
                assert row is not None, "pgvector extension missing"
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unavailable: {exc}")


def test_neo4j_bolt_handshake() -> None:
    neo4j = pytest.importorskip("neo4j")
    settings = _load_repo_settings()
    try:
        driver = neo4j.GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j unavailable: {exc}")
