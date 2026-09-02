"""CLI entrypoint for the eval harness (M17)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from mini_claude_code.eval.runner import default_cases_dir, run_all_cases, run_case_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run mini-claude-code agent eval cases (fake LLM, no network)."
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
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="mcc-eval-") as tmp:
        workspace = Path(tmp)
        if args.case:
            result = run_case_file(args.case.resolve(), workspace=workspace)
            results = [result]
        else:
            cases_dir = args.cases_dir or default_cases_dir()
            results = run_all_cases(cases_dir, workspace=workspace)

    failed = 0
    skipped = 0
    for result in results:
        if result.skipped:
            skipped += 1
            print(f"SKIP  {result.name}: {result.reason}")
            continue
        if result.passed:
            print(f"PASS  {result.name}")
        else:
            failed += 1
            print(f"FAIL  {result.name}: {result.reason}", file=sys.stderr)

    print(f"\n{len(results) - failed - skipped} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
