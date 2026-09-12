"""M38 integration: live GitHub Checks poll (skip without GH_TOKEN)."""

from __future__ import annotations

import json
import os

import pytest

from mini_claude_code.config import Settings, get_settings, repo_root
from mini_claude_code.tools.remote_ci import wait_for_checks_impl

pytestmark = pytest.mark.integration


def test_live_wait_for_checks_optional() -> None:
    """Opt-in live poll: set M38_LIVE_PR and GH_TOKEN.

    Example:
      M38_LIVE_PR=1 GH_TOKEN=... M38_PR_NUMBER=123 \\
        pytest -m integration tests/integration/test_m38_remote_ci_live.py
    """
    if os.environ.get("M38_LIVE_PR", "").strip() not in {"1", "true", "yes"}:
        pytest.skip("set M38_LIVE_PR=1 and M38_PR_NUMBER to run live poll")
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        pytest.skip("GH_TOKEN required for live remote CI poll")
    pr_raw = os.environ.get("M38_PR_NUMBER", "").strip()
    if not pr_raw.isdigit():
        pytest.skip("M38_PR_NUMBER must be an integer PR number")

    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        SHIP_REMOTE_CI=True,
        PR_DRY_RUN=False,
        GH_TOKEN=token,
        SHIP_REMOTE_CI_TIMEOUT_SEC=float(
            os.environ.get("M38_TIMEOUT_SEC", "60")
        ),
        SHIP_REMOTE_CI_POLL_SEC=2.0,
        SHIP_REMOTE_CI_HITL=False,
    )
    out = wait_for_checks_impl(
        pr_number=int(pr_raw),
        workspace_root=repo_root(),
        settings=settings,
    )
    data = json.loads(out)
    assert data["state"] in {"green", "red", "timed_out", "skipped"}
    assert "summary" in data
