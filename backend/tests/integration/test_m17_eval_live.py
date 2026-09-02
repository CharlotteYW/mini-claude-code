"""M17 integration: bundled eval cases + optional live skip."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mini_claude_code.config import get_settings, repo_root
from mini_claude_code.eval.runner import default_cases_dir, run_all_cases, run_eval_case
from mini_claude_code.eval.cases import load_eval_case

pytestmark = pytest.mark.integration


def test_bundled_fake_eval_cases_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    results = run_all_cases(default_cases_dir(), workspace=tmp_path)
    get_settings.cache_clear()
    for result in results:
        if result.skipped:
            continue
        assert result.passed, result.reason


def test_mcc_eval_script_cases_exist() -> None:
    cases = list(default_cases_dir().glob("*.yaml"))
    assert len(cases) >= 2
    names = {load_eval_case(p).name for p in cases}
    assert "tool_path_add" in names
    assert "plan_mode_deny_write" in names


@pytest.mark.skipif(
    not os.environ.get("LLM_PROVIDER"),
    reason="live eval needs LLM_PROVIDER",
)
def test_live_smoke_case_skips_without_keys() -> None:
    case = load_eval_case(
        repo_root() / "backend" / "evals" / "cases" / "live_smoke.yaml"
    )
    assert case.live
    result = run_eval_case(case, workspace=Path("/tmp"))
    assert result.skipped
