"""M0 smoke entrypoint: resolve provider/model, construct chat client, optional ping."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mini_claude_code.config import get_settings
from mini_claude_code.llm import create_chat_model


def _load_dotenv_from_repo_root() -> None:
    """Prefer repo-root .env regardless of cwd (scripts/run.sh vs uv run)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    here = Path(__file__).resolve()
    # .../backend/src/mini_claude_code/smoke.py -> repo root is parents[3]
    repo_root = here.parents[3]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test LLM factory + print active provider/model."
    )
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Send a one-token hello invoke (needs reachable provider/credentials).",
    )
    args = parser.parse_args(argv)

    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    print("mini-claude-code smoke (M0)")
    print(f"  provider: {settings.llm_provider}")
    print(f"  model:    {settings.llm_model}")

    try:
        model = create_chat_model(settings)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"  client:   {type(model).__module__}.{type(model).__name__}")
    print("  construct: OK")

    if args.ping:
        print("  ping: invoking model...")
        try:
            result = model.invoke("Reply with exactly: pong")
            content = getattr(result, "content", result)
            preview = str(content)[:200].replace("\n", " ")
            print(f"  ping: OK — {preview!r}")
        except Exception as exc:  # noqa: BLE001 — smoke should surface any provider error
            print(f"  ping: FAILED — {exc}", file=sys.stderr)
            return 1
    else:
        print("  ping: skipped (pass --ping to invoke)")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
