"""M23 unit tests: plugin pack expansion (skills / MCP / subagents merge)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mini_claude_code.agent.plugins import (
    collect_plugin_mcp_connections,
    collect_plugin_skill_defs,
    collect_plugin_subagent_defs,
    load_plugin_manifest,
    merge_mcp_connections,
    plugin_examples_dir,
    resolve_plugins,
)
from mini_claude_code.agent.skills import load_skill_defs
from mini_claude_code.agent.subagents import load_subagent_defs
from mini_claude_code.config import Settings
from mini_claude_code.tools.mcp_loader import resolve_mcp_connections

pytestmark = pytest.mark.unit


def test_parse_docs_mcp_and_research_manifests() -> None:
    docs = load_plugin_manifest(plugin_examples_dir() / "docs-mcp" / "plugin.yaml")
    assert docs.id == "docs-mcp"
    assert "fake_docs" in docs.mcp
    assert docs.mcp["fake_docs"]["preset"] == "fake_docs"
    assert "docs" in docs.slash_commands

    research = load_plugin_manifest(plugin_examples_dir() / "research" / "plugin.yaml")
    assert research.skill_refs == ["skills/doc-research"]
    assert research.subagent_refs == ["subagents/doc-scout.yaml"]
    assert "research" in research.slash_commands


def test_reject_bad_skills_type(tmp_path: Path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "plugin.yaml").write_text(
        yaml.safe_dump({"name": "bad", "skills": "not-a-list"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="skills must be a list"):
        load_plugin_manifest(d / "plugin.yaml")


def test_plugin_skills_merge_into_catalog() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "research" / "plugin.yaml")
    extra = collect_plugin_skill_defs([pack])
    assert "doc-research" in extra
    assert "Playbook for researching" in extra["doc-research"].description


def test_skill_collision_with_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    skill_dir = ws / "skills" / "doc-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: doc-research\ndescription: workspace copy\n---\n\nbody\n",
        encoding="utf-8",
    )
    pack = load_plugin_manifest(plugin_examples_dir() / "research" / "plugin.yaml")
    extra = collect_plugin_skill_defs([pack])
    with pytest.raises(ValueError, match="Duplicate skill"):
        load_skill_defs(ws, extra=extra)


def test_mcp_preset_materialize() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "docs-mcp" / "plugin.yaml")
    conns = collect_plugin_mcp_connections([pack])
    assert "fake_docs" in conns
    assert conns["fake_docs"]["transport"] == "stdio"
    assert Path(conns["fake_docs"]["args"][0]).name == "fake_docs.py"


def test_mcp_merge_collision_with_settings() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "docs-mcp" / "plugin.yaml")
    base = {"fake_docs": {"transport": "stdio", "command": "x", "args": []}}
    with pytest.raises(ValueError, match="Duplicate MCP server"):
        merge_mcp_connections(base, [pack])


def test_subagent_merge_from_plugin(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "subagents").mkdir(parents=True)
    # Don't seed explore — empty dir still gets ensure_example_subagents explore
    pack = load_plugin_manifest(plugin_examples_dir() / "research" / "plugin.yaml")
    extra = collect_plugin_subagent_defs([pack])
    assert "doc-scout" in extra
    defs = load_subagent_defs(ws, extra=extra)
    assert "doc-scout" in defs
    assert "explore" in defs  # workspace seed


def test_subagent_collision(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    sub = ws / "subagents"
    sub.mkdir(parents=True)
    (sub / "doc-scout.yaml").write_text(
        "name: doc-scout\ndescription: workspace\ntools: [read_file]\n",
        encoding="utf-8",
    )
    pack = load_plugin_manifest(plugin_examples_dir() / "research" / "plugin.yaml")
    extra = collect_plugin_subagent_defs([pack])
    with pytest.raises(ValueError, match="Duplicate subagent"):
        load_subagent_defs(ws, extra=extra)


def test_plugins_disabled_no_plugin_mcp(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    settings = Settings(
        _env_file=None,
        plugins_enabled=False,
        workspace_root=str(ws),
        mcp_use_demo=False,
        mcp_use_fake_docs=False,
        mcp_config="",
        mcp_config_path="",
    )
    packs = resolve_plugins(settings, workspace_root=ws)
    assert packs == []
    assert resolve_mcp_connections(settings, plugins=packs) == {}


def test_multi_pack_no_collision(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    # Point extra_roots at package examples (no seed into ws required)
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    packs = resolve_plugins(
        settings,
        workspace_root=ws,
        extra_roots=[plugin_examples_dir()],
        seed_examples=False,
    )
    # examples dir has review/, docs-mcp/, research/ as children — discover scans
    # plugins_root/*/plugin.yaml so extra_roots must be a root containing pack dirs.
    # plugin_examples_dir() IS that root.
    ids = {p.id for p in packs}
    assert {"review", "docs-mcp", "research"} <= ids
    skills = collect_plugin_skill_defs(packs)
    mcp = collect_plugin_mcp_connections(packs)
    subs = collect_plugin_subagent_defs(packs)
    assert "doc-research" in skills
    assert "fake_docs" in mcp
    assert "doc-scout" in subs


def test_ensure_seed_copies_examples(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    packs = resolve_plugins(settings, workspace_root=ws, seed_examples=True)
    ids = {p.id for p in packs}
    assert "review" in ids
    assert "docs-mcp" in ids
    assert "research" in ids
    assert (ws / "plugins" / "docs-mcp" / "plugin.yaml").is_file()
