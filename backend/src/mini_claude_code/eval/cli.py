"""CLI entrypoint for the eval harness (M17) + retrieval quality (M36)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from mini_claude_code.eval.runner import default_cases_dir, run_all_cases, run_case_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run mini-claude-code eval: fake-LLM agent cases (M17) and/or "
            "retrieval hit@k on a golden corpus (M36)."
        )
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=None,
        help="Directory of *.yaml eval cases (default: backend/evals/cases).",
    )
    parser.add_argument(
        "--case",
        type=Path,
        default=None,
        help="Run a single case file instead of the whole directory.",
    )
    parser.add_argument(
        "--retrieval",
        action="store_true",
        help="M36: ingest golden corpus and report retrieval hit@k (needs ES/Postgres).",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help="Override golden corpus directory (default: backend/evals/corpus).",
    )
    parser.add_argument(
        "--qrels",
        type=Path,
        default=None,
        help="Override qrels YAML (default: backend/evals/qrels/rag_smoke.yaml).",
    )
    parser.add_argument(
        "--skip-agent-cases",
        action="store_true",
        help="With --retrieval: skip M17 agent YAML cases.",
    )
    args = parser.parse_args(argv)

    if args.skip_agent_cases and not args.retrieval:
        print("ERROR: --skip-agent-cases requires --retrieval", file=sys.stderr)
        return 1

    failed = 0
    skipped = 0
    agent_total = 0

    do_agents = not args.skip_agent_cases
    # Preserve M17 default: no flags → agent cases only.
    if not args.retrieval and not do_agents:
        do_agents = True

    if do_agents:
        with tempfile.TemporaryDirectory(prefix="mcc-eval-") as tmp:
            workspace = Path(tmp)
            if args.case:
                result = run_case_file(args.case.resolve(), workspace=workspace)
                results = [result]
            else:
                cases_dir = args.cases_dir or default_cases_dir()
                results = run_all_cases(cases_dir, workspace=workspace)

        for result in results:
            agent_total += 1
            if result.skipped:
                skipped += 1
                print(f"SKIP  {result.name}: {result.reason}")
                continue
            if result.passed:
                print(f"PASS  {result.name}")
            else:
                failed += 1
                print(f"FAIL  {result.name}: {result.reason}", file=sys.stderr)

        print(
            f"\n{agent_total - failed - skipped} passed, {failed} failed, "
            f"{skipped} skipped (agent cases)"
        )

    if args.retrieval:
        from dotenv import load_dotenv

        from mini_claude_code.config import get_settings, repo_root
        from mini_claude_code.eval.retrieval import (
            default_corpus_dir,
            default_qrels_path,
            run_retrieval_eval,
        )

        env_path = repo_root() / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
        get_settings.cache_clear()
        settings = get_settings()

        with tempfile.TemporaryDirectory(prefix="mcc-eval-rag-") as tmp:
            workspace = Path(tmp)
            try:
                report = run_retrieval_eval(
                    workspace=workspace,
                    corpus_dir=(args.corpus_dir or default_corpus_dir()).resolve(),
                    qrels_path=(args.qrels or default_qrels_path()).resolve(),
                    settings=settings,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  retrieval_eval: {exc}", file=sys.stderr)
                return 1
            print()
            print(report.format())
            failed += report.failed

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
