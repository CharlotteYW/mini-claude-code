"""M12 integration: run_subagent with real explore.yaml (fake LLM child)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.subagents import build_subagent_tools, load_subagent_defs
from mini_claude_code.config import Settings, get_settings, repo_root
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.integration


class _Bound:
    def __init__(self) -> None:
        self.n = 0

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        self.n += 1
        # Parent first turn → call subagent; child turns → final text.
        has_tool = any(isinstance(m, ToolMessage) for m in messages)
        if not has_tool and self.n == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_subagent",
                        "args": {
                            "name": "explore",
                            "task": "List what explore is for in one sentence.",
                        },
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Explore subagent finished (integration).")


class _LLM:
    def bind_tools(self, _tools: Any) -> _Bound:
        return _Bound()


def test_repo_explore_yaml_loads() -> None:
    workspace = repo_root() / "workspace"
    defs = load_subagent_defs(workspace)
    assert "explore" in defs
    assert "read_file" in defs["explore"].tools


def test_parent_delegates_to_explore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Copy minimal explore def into tmp workspace so we do not touch real files.
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    sub = tmp_path / "subagents"
    sub.mkdir()
    repo_explore = repo_root() / "workspace" / "subagents" / "explore.yaml"
    sub.joinpath("explore.yaml").write_text(
        repo_explore.read_text(encoding="utf-8"), encoding="utf-8"
    )

    settings = Settings(llm_provider="ollama", llm_model="x")
    llm = _LLM()
    tools = [
        *build_coding_tools(tmp_path),
        *build_subagent_tools(tmp_path, settings=settings, llm=llm),
    ]
    graph = build_agent_graph(
        llm=llm,
        tools=tools,
        ask_callback=lambda _n, _a: True,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="Use explore subagent.")]},
        config={"recursion_limit": 12},
    )
    assert any(
        isinstance(m, ToolMessage) and "subagent:explore" in str(m.content)
        for m in result["messages"]
    )
    get_settings.cache_clear()
