"""M12 unit tests: YAML subagent loader + isolated run_subagent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.subagents import (
    build_subagent_tools,
    load_subagent_def,
    load_subagent_defs,
    tools_for_allowlist,
    build_tool_catalog,
)
from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.unit


def test_load_explore_yaml(tmp_path: Path) -> None:
    sub = tmp_path / "subagents"
    sub.mkdir()
    (sub / "explore.yaml").write_text(
        """
name: explore
description: Read-only explorer
tools: [read_file, glob_files, grep_files]
system: |
  Be brief.
""".strip(),
        encoding="utf-8",
    )
    defs = load_subagent_defs(tmp_path)
    assert "explore" in defs
    assert defs["explore"].tools == ("read_file", "glob_files", "grep_files")
    assert "brief" in defs["explore"].system.lower() or "Be brief" in defs["explore"].system


def test_unknown_subagent_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    (tmp_path / "subagents").mkdir()
    tools = {
        t.name: t
        for t in build_subagent_tools(
            tmp_path,
            settings=Settings(llm_provider="ollama", llm_model="x"),
            llm=_FakeLLMParent(),
        )
    }
    out = tools["run_subagent"].invoke({"name": "nope", "task": "find x"})
    assert "ERROR" in out
    assert "unknown" in out.lower()
    get_settings.cache_clear()


def test_explore_allowlist_excludes_write(tmp_path: Path) -> None:
    settings = Settings(llm_provider="ollama", llm_model="x")
    catalog = build_tool_catalog(tmp_path, settings)
    selected = tools_for_allowlist(
        catalog, ["read_file", "glob_files", "grep_files"]
    )
    names = {t.name for t in selected}
    assert names == {"read_file", "glob_files", "grep_files"}
    assert "write_file" not in names
    assert "run_shell" not in names


class _FakeBoundChild:
    """Child answers without tools — proves isolation + summary return."""

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        # Must not see a leaked parent-only phrase if isolation works.
        blob = " ".join(str(getattr(m, "content", "")) for m in messages)
        assert "PARENT_SECRET_TRANSCRIPT" not in blob
        assert any(isinstance(m, HumanMessage) for m in messages)
        return AIMessage(content="Found note.txt with hello.")


class _FakeLLMChild:
    def bind_tools(self, _tools: Any) -> _FakeBoundChild:
        return _FakeBoundChild()


class _FakeBoundParent:
    def __init__(self) -> None:
        self.n = 0

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        self.n += 1
        if self.n == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_subagent",
                        "args": {
                            "name": "explore",
                            "task": "Summarize note.txt",
                        },
                        "id": "s1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Parent done with subagent result.")


class _FakeLLMParent:
    def bind_tools(self, _tools: Any) -> _FakeBoundParent:
        return _FakeBoundParent()


def test_run_subagent_isolated_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    sub = tmp_path / "subagents"
    sub.mkdir()
    (sub / "explore.yaml").write_text(
        """
name: explore
description: Read-only explorer
tools: [read_file, glob_files, grep_files]
system: You explore read-only.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")

    settings = Settings(llm_provider="ollama", llm_model="x")
    # Parent tool uses child fake LLM via closure.
    sub_tools = build_subagent_tools(
        tmp_path, settings=settings, llm=_FakeLLMChild(), plan_mode=False
    )
    parent_tools = [*build_coding_tools(tmp_path), *sub_tools]

    graph = build_agent_graph(
        llm=_FakeLLMParent(),
        tools=parent_tools,
        plan_mode=False,
        ask_callback=lambda _n, _a: True,
    )
    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content="PARENT_SECRET_TRANSCRIPT — delegate explore"
                )
            ]
        },
        config={"recursion_limit": 10},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert "subagent:explore" in str(tool_msgs[0].content)
    assert "Found note.txt" in str(tool_msgs[0].content)
    assert "PARENT_SECRET_TRANSCRIPT" not in str(tool_msgs[0].content)

    names = set(graph.get_graph().nodes)
    assert "call_model" in names and "tools" in names
    get_settings.cache_clear()


def test_load_subagent_def_requires_description(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("name: x\ntools: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="description"):
        load_subagent_def(path)
