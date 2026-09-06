"""M25 unit tests: install, version/requires, trust gates."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mini_claude_code.agent.plugin_install import (
    check_requires,
    install_plugin_from_path,
    parse_version,
)
from mini_claude_code.agent.plugin_trust import (
    TrustEntry,
    load_trust_store,
    save_trust_store,
    set_trust,
)
from mini_claude_code.agent.plugins import (
    apply_trust_capabilities,
    collect_plugin_mcp_connections,
    load_plugin_manifest,
    plugin_examples_dir,
    resolve_plugins,
    strip_shell_hook_entries,
)
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


def test_parse_version() -> None:
    assert parse_version("0.1.0") == (0, 1, 0)
    assert parse_version("v1.2") == (1, 2, 0)


def test_check_requires_ok_and_fail() -> None:
    check_requires({"mini_claude_code": ">=0.1.0"}, package_version="0.1.0")
    with pytest.raises(ValueError, match="requires"):
        check_requires({"mini_claude_code": ">=9.0.0"}, package_version="0.1.0")


def test_manifest_version_fields() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "review" / "plugin.yaml")
    assert pack.version == "0.1.0"
    assert "mini_claude_code" in pack.requires


def test_install_from_path_copies_and_disables(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    src = plugin_examples_dir() / "research"
    dest = install_plugin_from_path(src, workspace_root=ws, force=False)
    assert (dest / "plugin.yaml").is_file()
    store = load_trust_store(ws)
    entry = store.get("research")
    assert entry is not None
    assert entry.enabled is False
    assert entry.allow_mcp is False
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    active = resolve_plugins(settings, workspace_root=ws, seed_examples=False)
    assert "research" not in {p.id for p in active}


def test_install_refuses_overwrite(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    src = plugin_examples_dir() / "review"
    install_plugin_from_path(src, workspace_root=ws)
    with pytest.raises(ValueError, match="already installed"):
        install_plugin_from_path(src, workspace_root=ws, force=False)


def test_trust_enable_with_mcp(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    install_plugin_from_path(plugin_examples_dir() / "docs-mcp", workspace_root=ws)
    store = load_trust_store(ws)
    set_trust(store, "docs-mcp", enabled=True, allow_mcp=True, allow_shell_hooks=False)
    save_trust_store(store, ws)
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    active = resolve_plugins(settings, workspace_root=ws, seed_examples=False)
    assert "docs-mcp" in {p.id for p in active}
    conns = collect_plugin_mcp_connections(active)
    assert "fake_docs" in conns


def test_capability_strips_mcp_and_shell(tmp_path: Path) -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "shell-hooks" / "plugin.yaml")
    store = load_trust_store(tmp_path)
    store.packs["shell-hooks"] = TrustEntry(
        enabled=True, allow_shell_hooks=False, allow_mcp=False
    )
    gated = apply_trust_capabilities(pack, store)
    assert gated.mcp == {}
    assert strip_shell_hook_entries(pack.hooks) == gated.hooks
    assert not any(
        isinstance(x, dict) and x.get("type") == "script"
        for items in gated.hooks.values()
        for x in items
    )


def test_list_trust_yaml_roundtrip(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "plugins").mkdir(parents=True)
    store = load_trust_store(ws)
    set_trust(store, "demo", enabled=True, allow_mcp=True)
    path = save_trust_store(store, ws)
    assert path.is_file()
    data = yaml.safe_load(path.read_text())
    assert data["packs"]["demo"]["allow_mcp"] is True
