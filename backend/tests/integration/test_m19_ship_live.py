"""M19 integration: fake ship_check loop then dry-run PR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.config import Settings
from mini_claude_code.tools.github_pr import build_github_pr_tools
from mini_claude_code.tools.ship import (
    ShipGate,
    apply_ship_gate_to_tools,
    build_ship_tools,
)

pytestmark = pytest.mark.integration


class _ScriptedBound:
    def __init__(self) -> None:
        self.n = 0

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        self.n += 1
        # After any tool result, finish with a short summary once ship+pr done.
        tool_names = [
            m.name for m in messages if isinstance(m, ToolMessage)
        ]
        if "open_pull_request" in tool_names:
            return AIMessage(content="Shipped via dry-run PR.")
        if "ship_check" in tool_names:
            # After green check, open PR
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "open_pull_request",
                        "args": {"title": "M19 demo", "body": "gate passed"},
                        "id": "pr1",
                        "type": "tool_call",
                    }
                ],
            )
        # First turn: ship_check
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "ship_check",
                    "args": {},
                    "id": "sc1",
                    "type": "tool_call",
                }
            ],
        )


class _FakeLLM:
    def __init__(self) -> None:
        self._bound = _ScriptedBound()

    def bind_tools(self, _tools: Any) -> _ScriptedBound:
        return self._bound


def test_fake_llm_ship_check_then_dry_run_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()

    settings = Settings(
        workspace_root=str(tmp_path),
        pr_dry_run=True,
        ship_require_green=True,
        ship_mode="pr",
        plugins_enabled=False,
    )
    gate = ShipGate(require_green=True, max_fix_iters=3)

    def always_pass(_root: Path) -> tuple[int, str]:
        return 0, "ok"

    ship_tools, gate = build_ship_tools(
        tmp_path,
        settings=settings,
        gate=gate,
        format_runner=always_pass,
        test_runner=always_pass,
        project_root=tmp_path,
    )
    pr_tools = apply_ship_gate_to_tools(
        build_github_pr_tools(tmp_path, settings=settings),
        gate,
    )
    tools = [*ship_tools, *pr_tools]

    graph = build_agent_graph(
        settings=settings,
        llm=_FakeLLM(),
        tools=tools,
        plan_mode=False,
        apply_tool_permissions=False,
        apply_tool_hooks=False,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="ship it")]},
        config={"recursion_limit": 10},
    )
    transcript = "\n".join(str(m.content) for m in result["messages"])
    assert "dry_run" in transcript or "Shipped" in transcript
    assert gate.last_passed is True
    get_settings.cache_clear()


def test_live_ship_check_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Optional: real ship_check on this repo — skip if SKIP_M19_LIVE=1."""
    import os

    if os.environ.get("SKIP_M19_LIVE", "1") == "1":
        pytest.skip("set SKIP_M19_LIVE=0 to run live ship_check against repo")
    from mini_claude_code.config import repo_root
    from mini_claude_code.tools.ship import ship_check_impl

    out = ship_check_impl(project_root=repo_root())
    data = json.loads(out.split("\n\n")[0])
    assert "ok" in data
