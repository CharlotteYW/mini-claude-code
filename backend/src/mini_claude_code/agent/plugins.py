"""Declarative plugin packs (M16): scan manifests, merge hooks, slash registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mini_claude_code.config import Settings, get_settings, resolve_workspace_root

logger = logging.getLogger(__name__)

PLUGIN_MANIFEST = "plugin.yaml"


@dataclass
class PluginPack:
    """One plugin directory with a parsed manifest."""

    id: str
    name: str
    description: str
    slash_commands: dict[str, dict[str, Any]]
    hooks: dict[str, list[str]]
    path: Path


def plugin_examples_dir() -> Path:
    return Path(__file__).resolve().parent / "plugin_examples"


def discover_plugin_manifests(plugins_root: Path) -> list[Path]:
    """Return plugin.yaml paths under ``plugins_root/*/``."""
    if not plugins_root.is_dir():
        return []
    paths: list[Path] = []
    for child in sorted(plugins_root.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / PLUGIN_MANIFEST
        if manifest.is_file():
            paths.append(manifest)
    return paths


def load_plugin_manifest(path: Path) -> PluginPack:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Plugin manifest must be a mapping: {path}")
    plugin_id = path.parent.name
    name = str(data.get("name") or plugin_id)
    description = str(data.get("description") or "").strip()
    raw_slash = data.get("slash_commands") or {}
    if not isinstance(raw_slash, dict):
        raise ValueError(f"slash_commands must be a mapping in {path}")
    hooks_raw = data.get("hooks") or {}
    if hooks_raw and not isinstance(hooks_raw, dict):
        raise ValueError(f"hooks must be a mapping in {path}")
    hooks = _normalize_hook_section(hooks_raw)
    slash_commands: dict[str, dict[str, Any]] = {}
    for cmd_name, spec in raw_slash.items():
        key = str(cmd_name).lstrip("/")
        if not key:
            raise ValueError(f"Invalid slash command name in {path}")
        if not isinstance(spec, dict):
            raise ValueError(f"slash_commands.{key} must be a mapping in {path}")
        template = spec.get("template")
        if not template or not str(template).strip():
            raise ValueError(f"slash_commands.{key}.template required in {path}")
        slash_commands[key] = {
            "description": str(spec.get("description") or "").strip(),
            "template": str(template),
        }
    return PluginPack(
        id=plugin_id,
        name=name,
        description=description,
        slash_commands=slash_commands,
        hooks=hooks,
        path=path,
    )


def _normalize_hook_section(hooks_raw: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "pre_tool_use": [],
        "post_tool_use": [],
        "stop": [],
    }
    for key in out:
        items = hooks_raw.get(key) or []
        if not isinstance(items, list):
            raise ValueError(f"hooks.{key} must be a list")
        out[key] = [str(i) for i in items]
    return out


def load_plugins_from_paths(paths: list[Path]) -> list[PluginPack]:
    return [load_plugin_manifest(p) for p in paths]


def discover_plugins(
    workspace_root: Path,
    *,
    extra_roots: list[Path] | None = None,
) -> list[PluginPack]:
    """Scan ``workspace/plugins`` and optional extra roots (tests)."""
    manifests: list[Path] = discover_plugin_manifests(workspace_root / "plugins")
    for root in extra_roots or []:
        manifests.extend(discover_plugin_manifests(root))
    return load_plugins_from_paths(manifests)


def resolve_plugins(
    settings: Settings | None = None,
    *,
    workspace_root: Path | None = None,
    extra_roots: list[Path] | None = None,
) -> list[PluginPack]:
    settings = settings or get_settings()
    if not settings.plugins_enabled:
        return []
    root = workspace_root or resolve_workspace_root(settings)
    return discover_plugins(root, extra_roots=extra_roots)


def merge_hook_config_dicts(
    base: dict[str, Any] | None,
    plugins: list[PluginPack],
) -> dict[str, list[str]]:
    """Append plugin hook id lists after base; dedupe within each list (first wins)."""
    merged: dict[str, list[str]] = {
        "pre_tool_use": list((base or {}).get("pre_tool_use") or []),
        "post_tool_use": list((base or {}).get("post_tool_use") or []),
        "stop": list((base or {}).get("stop") or []),
    }
    for plugin in plugins:
        for key in merged:
            merged[key].extend(plugin.hooks.get(key) or [])
    for key in merged:
        seen: set[str] = set()
        deduped: list[str] = []
        for hid in merged[key]:
            if hid in seen:
                continue
            seen.add(hid)
            deduped.append(hid)
        merged[key] = deduped
    return merged


def _load_base_hooks_dict(
    settings: Settings,
    workspace_root: Path,
) -> dict[str, list[str]] | None:
    path_raw = settings.hooks_config_path.strip()
    if path_raw:
        data = yaml.safe_load(Path(path_raw).read_text(encoding="utf-8")) or {}
        return merge_hook_config_dicts(data if isinstance(data, dict) else {}, [])
    default_path = workspace_root / "hooks.yaml"
    if default_path.is_file():
        data = yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
        return merge_hook_config_dicts(data if isinstance(data, dict) else {}, [])
    if settings.hooks_use_demo:
        return {
            "pre_tool_use": ["block_dangerous_shell"],
            "post_tool_use": ["redact_secret_pattern", "append_audit_marker"],
            "stop": ["log_stop"],
        }
    return None


def resolve_merged_hooks_dict(
    settings: Settings | None = None,
    *,
    workspace_root: Path | None = None,
    plugins: list[PluginPack] | None = None,
) -> dict[str, list[str]] | None:
    """Base hooks config + appended plugin hook sections."""
    settings = settings or get_settings()
    root = workspace_root or resolve_workspace_root(settings)
    packs = (
        plugins
        if plugins is not None
        else resolve_plugins(settings, workspace_root=root)
    )
    base = _load_base_hooks_dict(settings, root)
    if base is None and not packs:
        return None
    return merge_hook_config_dicts(base, packs)


def build_slash_registry(plugins: list[PluginPack]) -> dict[str, dict[str, str]]:
    """Map command name (no slash) → {description, template, plugin_id}.

    Raises ValueError on duplicate command names across plugins.
    """
    registry: dict[str, dict[str, str]] = {}
    for plugin in plugins:
        for cmd_name, spec in plugin.slash_commands.items():
            if cmd_name in registry:
                other = registry[cmd_name]["plugin_id"]
                raise ValueError(
                    f"Duplicate slash command /{cmd_name!r} "
                    f"(plugins {other!r} and {plugin.id!r})"
                )
            registry[cmd_name] = {
                "description": spec["description"],
                "template": spec["template"],
                "plugin_id": plugin.id,
            }
    return registry
