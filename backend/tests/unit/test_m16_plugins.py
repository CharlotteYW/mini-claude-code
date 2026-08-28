"""M16 unit tests: plugin parse, slash expand, hook merge, /help."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_claude_code.agent.hooks import load_hook_registry_from_dict, resolve_hook_registry
from mini_claude_code.agent.plugins import (
    load_plugin_manifest,
    merge_hook_config_dicts,
    plugin_examples_dir,
    resolve_merged_hooks_dict,
    resolve_plugins,
    build_slash_registry,
)
from mini_claude_code.agent.slash_commands import (
    dispatch_slash_input,
    expand_template,
    format_slash_list,
    parse_slash_parts,
)
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


def test_load_review_plugin_manifest() -> None:
    path = plugin_examples_dir() / "review" / "plugin.yaml"
    pack = load_plugin_manifest(path)
    assert pack.id == "review"
    assert "review" in pack.slash_commands
    assert "block_dangerous_shell" in pack.hooks["pre_tool_use"]


def test_build_slash_registry_collision() -> None:
    pack_a = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    with pytest.raises(ValueError, match="Duplicate"):
        build_slash_registry([pack_a, pack_a])


def test_expand_template_args_placeholder() -> None:
    out = expand_template("Hello {{args}}", "world")
    assert out == "Hello world"


def test_expand_template_append_args() -> None:
    out = expand_template("Hello", "extra")
    assert "Hello" in out
    assert "extra" in out


def test_dispatch_review_expands() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    reg = build_slash_registry([pack])
    d = dispatch_slash_input("/review focus on tests", reg, plugins=[pack])
    assert d.kind == "invoke"
    assert "structured review" in d.prompt.lower()
    assert "focus on tests" in d.prompt


def test_dispatch_help_lists_no_invoke() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    reg = build_slash_registry([pack])
    d = dispatch_slash_input("/help", reg, plugins=[pack])
    assert d.kind == "list"
    assert "/review" in d.list_text
    assert "plugin: review" in d.list_text


def test_dispatch_plugins_same_as_help() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    reg = build_slash_registry([pack])
    help_d = dispatch_slash_input("/help", reg, plugins=[pack])
    plugins_d = dispatch_slash_input("/plugins", reg, plugins=[pack])
    assert help_d.list_text == plugins_d.list_text


def test_dispatch_unknown_slash_errors() -> None:
    with pytest.raises(ValueError, match="Unknown slash"):
        dispatch_slash_input("/nope", {}, plugins=[])


def test_parse_slash_parts() -> None:
    assert parse_slash_parts("hello") is None
    assert parse_slash_parts("/review x") == ("review", "x")


def test_merge_hook_config_dedupes() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    merged = merge_hook_config_dicts(
        {"pre_tool_use": ["block_dangerous_shell"]},
        [pack],
    )
    assert merged["pre_tool_use"].count("block_dangerous_shell") == 1


def test_resolve_merged_hooks_includes_plugin(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    plug_dir = ws / "plugins" / "review"
    plug_dir.mkdir(parents=True)
    src = plugin_examples_dir() / "review" / "plugin.yaml"
    (plug_dir / "plugin.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    merged = resolve_merged_hooks_dict(settings, workspace_root=ws)
    assert merged is not None
    assert "block_dangerous_shell" in merged["pre_tool_use"]
    reg = resolve_hook_registry(settings, workspace_root=ws)
    assert not reg.empty


def test_plugins_disabled_empty(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    plug_dir = ws / "plugins" / "review"
    plug_dir.mkdir(parents=True)
    src = plugin_examples_dir() / "review" / "plugin.yaml"
    (plug_dir / "plugin.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings(_env_file=None, plugins_enabled=False, workspace_root=str(ws))
    assert resolve_plugins(settings, workspace_root=ws) == []


def test_format_slash_list_empty() -> None:
    text = format_slash_list({})
    assert "none" in text.lower()
