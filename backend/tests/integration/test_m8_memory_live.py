"""M8 integration: Neo4j fact remember/recall (skip if Neo4j down)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.memory.neo4j_facts import recall_facts, remember_fact

pytestmark = pytest.mark.integration


def _load_repo_settings() -> Settings:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    get_settings.cache_clear()
    return get_settings()


def _neo4j_or_skip(settings: Settings) -> None:
    neo4j = pytest.importorskip("neo4j")
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


def test_remember_and_recall_fact_roundtrip() -> None:
    settings = _load_repo_settings()
    _neo4j_or_skip(settings)
    token = f"m8-fact-{uuid4()}"
    stored = remember_fact(
        f"Integration preference codeword {token}",
        kind="test",
        settings=settings,
    )
    assert stored.id
    found = recall_facts(token, limit=5, settings=settings)
    assert any(token in f.text for f in found)
