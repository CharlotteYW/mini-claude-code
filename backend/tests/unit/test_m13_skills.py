"""M13 unit tests: skill parse, catalog, load_skill, inject view."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.skills import (
    CATALOG_MARKER,
    LOADED_MARKER,
    build_skill_tools,
    format_skills_catalog,
    inject_skills_view,
    load_skill_defs,
    parse_skill_md,
)
from mini_claude_code.tools.fs import build_coding_tools

pytestmark = pytest.mark.unit


def _write_skill(root: Path, name: str, description: str, body: str) -> Path:
    d = root / "skills" / name
    d.mkdir(parents=True)
    path = d / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_parse_skill_md(tmp_path: Path) -> None:
    path = _write_skill(tmp_path, "demo", "A demo skill", "# Hello\n\nFull body here.")
    defn = parse_skill_md(path)
    assert defn.name == "demo"
    assert defn.description == "A demo skill"
    assert "Full body here" in defn.body
    assert "name: demo" not in defn.body


def test_catalog_excludes_body(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo", "Short desc", "SECRET_BODY_SHOULD_NOT_APPEAR")
    defs = load_skill_defs(tmp_path)
    catalog = format_skills_catalog(defs)
    assert CATALOG_MARKER in catalog
    assert "demo" in catalog
    assert "Short desc" in catalog
    assert "SECRET_BODY" not in catalog


def test_load_skill_tool(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo", "Short desc", "FULL_INSTRUCTIONS")
    tools = {t.name: t for t in build_skill_tools(tmp_path)}
    out = tools["load_skill"].invoke({"name": "demo"})
    assert out.startswith("[skill:demo]")
    assert "FULL_INSTRUCTIONS" in out
    err = tools["load_skill"].invoke({"name": "missing"})
    assert "ERROR" in err
    assert "unknown" in err.lower()


def test_inject_skills_view_catalog_and_loaded(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo", "Short desc", "FULL_INSTRUCTIONS")
    messages = [
        HumanMessage(content="hi"),
        ToolMessage(
            content="[skill:demo]\nFULL_INSTRUCTIONS",
            name="load_skill",
            tool_call_id="t1",
        ),
    ]
    view = inject_skills_view(messages, tmp_path)
    texts = [str(m.content) for m in view if isinstance(m, SystemMessage)]
    assert any(CATALOG_MARKER in t for t in texts)
    assert any(LOADED_MARKER in t and "FULL_INSTRUCTIONS" in t for t in texts)
    # Catalog must not be the only place with body accidentally duplicated as catalog
    catalog_only = format_skills_catalog(load_skill_defs(tmp_path))
    assert "FULL_INSTRUCTIONS" not in catalog_only


class _FakeBound:
    def __init__(self) -> None:
        self.n = 0
        self.last_prompt: list[Any] = []

    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        self.n += 1
        self.last_prompt = list(messages)
        if self.n == 1:
            # Catalog should be present before any load.
            blob = " ".join(str(getattr(m, "content", "")) for m in messages)
            assert CATALOG_MARKER in blob
            assert "FULL_BODY_UNIQUE" not in blob
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "load_skill",
                        "args": {"name": "demo"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )
        blob = " ".join(str(getattr(m, "content", "")) for m in messages)
        assert "FULL_BODY_UNIQUE" in blob or any(
            isinstance(m, ToolMessage) and "FULL_BODY_UNIQUE" in str(m.content)
            for m in messages
        )
        return AIMessage(content="Loaded skill and ready.")


class _FakeLLM:
    def __init__(self) -> None:
        self.bound = _FakeBound()

    def bind_tools(self, _tools: Any) -> _FakeBound:
        return self.bound


def test_graph_progressive_disclosure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    from mini_claude_code.config import get_settings

    get_settings.cache_clear()
    _write_skill(tmp_path, "demo", "Short desc", "FULL_BODY_UNIQUE")

    llm = _FakeLLM()
    tools = [*build_coding_tools(tmp_path), *build_skill_tools(tmp_path)]
    graph = build_agent_graph(llm=llm, tools=tools, ask_callback=lambda _n, _a: True)
    result = graph.invoke(
        {"messages": [HumanMessage(content="Load the demo skill.")]},
        config={"recursion_limit": 10},
    )
    assert any(
        isinstance(m, ToolMessage) and "FULL_BODY_UNIQUE" in str(m.content)
        for m in result["messages"]
    )
    names = set(graph.get_graph().nodes)
    assert "call_model" in names and "tools" in names
    get_settings.cache_clear()
