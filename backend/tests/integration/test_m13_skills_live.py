"""M13 integration: packaged / workspace skill loads."""

from __future__ import annotations

import pytest

from mini_claude_code.agent.skills import load_skill_defs
from mini_claude_code.config import repo_root

pytestmark = pytest.mark.integration


def test_workspace_layout_skill_present() -> None:
    defs = load_skill_defs(repo_root() / "workspace")
    assert "workspace-layout" in defs
    assert "AGENT.md" in defs["workspace-layout"].body or "subagents" in defs[
        "workspace-layout"
    ].body
    catalog_bits = defs["workspace-layout"].description
    assert "workspace" in catalog_bits.lower() or "layout" in catalog_bits.lower()
