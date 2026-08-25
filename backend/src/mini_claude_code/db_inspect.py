"""Inspect Compose-backed stores (Postgres checkpointer + Neo4j).

Teaching helper: see what durable sessions actually look like in the DB,
without dumping opaque checkpoint blobs by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from mini_claude_code.config import Settings, get_settings

Target = Literal["all", "postgres", "neo4j"]

CHECKPOINT_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
)


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # …/backend/src/mini_claude_code → parents[3] is repo root
    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def inspect_postgres(
    settings: Settings, *, thread_id: str | None = None
) -> int:
    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg not installed (run ./scripts/setup.sh)", file=sys.stderr)
        return 1

    print("=== Postgres (LangGraph checkpointer) ===")
    print(f"  url: {settings.database_url}")
    try:
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                print("  tables:")
                for table in CHECKPOINT_TABLES:
                    cur.execute(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM information_schema.tables
                          WHERE table_schema = 'public' AND table_name = %s
                        )
                        """,
                        (table,),
                    )
                    exists = cur.fetchone()[0]
                    if not exists:
                        print(f"    {table}: (missing — run setup / agent once)")
                        continue
                    cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
                    print(f"    {table}: {cur.fetchone()[0]} rows")

                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'public' AND table_name = 'memory_notes'
                    )
                    """
                )
                if cur.fetchone()[0]:
                    cur.execute("SELECT count(*) FROM memory_notes")
                    print(f"    memory_notes: {cur.fetchone()[0]} rows (pgvector M8-B)")
                else:
                    print(
                        "    memory_notes: (missing — created on first remember_note)"
                    )

                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'public' AND table_name = 'checkpoints'
                    )
                    """
                )
                if not cur.fetchone()[0]:
                    print("  No checkpoints table yet.")
                    return 0

                print("  threads (checkpoint counts):")
                cur.execute(
                    """
                    SELECT thread_id,
                           count(*) AS n,
                           max(checkpoint->>'ts') AS last_ts
                    FROM checkpoints
                    GROUP BY thread_id
                    ORDER BY last_ts DESC NULLS LAST
                    LIMIT 30
                    """
                )
                rows = cur.fetchall()
                if not rows:
                    print("    (empty)")
                else:
                    for tid, n, last_ts in rows:
                        print(f"    {tid}: {n} checkpoints  last={last_ts}")

                if thread_id:
                    print(f"  detail thread_id={thread_id!r}:")
                    cur.execute(
                        """
                        SELECT checkpoint_id,
                               parent_checkpoint_id,
                               checkpoint->>'ts' AS ts,
                               metadata
                        FROM checkpoints
                        WHERE thread_id = %s
                        ORDER BY checkpoint->>'ts' DESC NULLS LAST
                        LIMIT 10
                        """,
                        (thread_id,),
                    )
                    detail = cur.fetchall()
                    if not detail:
                        print("    (no rows for this thread_id)")
                    else:
                        for cp_id, parent, ts, meta in detail:
                            print(
                                f"    id={cp_id} parent={parent} ts={ts}"
                            )
                            if meta:
                                print(f"      metadata={meta}")
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR: Postgres unreachable ({exc}). "
            "Start with: docker compose --env-file .env up -d",
            file=sys.stderr,
        )
        return 1
    return 0


def inspect_neo4j(settings: Settings) -> int:
    try:
        import neo4j
    except ImportError:
        print("ERROR: neo4j driver not installed (run ./scripts/setup.sh)", file=sys.stderr)
        return 1

    print("=== Neo4j (graph memory / Fact nodes — M8) ===")
    print(f"  uri: {settings.neo4j_uri}")
    try:
        driver = neo4j.GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            driver.verify_connectivity()
            with driver.session() as session:
                labels = session.run(
                    "CALL db.labels() YIELD label RETURN label ORDER BY label"
                ).value()
                rels = session.run(
                    "CALL db.relationshipTypes() YIELD relationshipType "
                    "RETURN relationshipType ORDER BY relationshipType"
                ).value()
                nodes = session.run("MATCH (n) RETURN count(n)").single()[0]
                edges = session.run("MATCH ()-[r]->() RETURN count(r)").single()[0]
                print(f"  labels: {labels or '(none)'}")
                print(f"  relationship types: {rels or '(none)'}")
                print(f"  nodes: {nodes}  relationships: {edges}")
                if nodes:
                    print("  sample nodes (limit 5):")
                    for record in session.run("MATCH (n) RETURN n LIMIT 5"):
                        print(f"    {record['n']}")
                else:
                    print("  (empty — no Fact nodes yet; try remember_fact via the agent)")
                facts = session.run(
                    "MATCH (f:Fact) RETURN f.text AS text, f.kind AS kind "
                    "ORDER BY f.created_at DESC LIMIT 5"
                )
                rows = list(facts)
                if rows:
                    print("  recent Fact nodes:")
                    for r in rows:
                        print(f"    [{r['kind']}] {r['text']}")
        finally:
            driver.close()
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR: Neo4j unreachable ({exc}). "
            "Start with: docker compose --env-file .env up -d",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Postgres checkpointer tables and/or Neo4j graph."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="all",
        choices=["all", "postgres", "neo4j"],
        help="Which store to inspect (default: all).",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Postgres only: show recent checkpoints for this session id.",
    )
    args = parser.parse_args(argv)

    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    target: Target = args.target
    codes: list[int] = []
    if target in ("all", "postgres"):
        codes.append(inspect_postgres(settings, thread_id=args.thread_id))
    if target in ("all", "neo4j"):
        if args.thread_id and target == "neo4j":
            print("Note: --thread-id applies to Postgres only.", file=sys.stderr)
        codes.append(inspect_neo4j(settings))
    return 1 if any(codes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
