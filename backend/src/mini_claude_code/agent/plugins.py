"""Declarative plugin packs (M16/M23): scan manifests, merge extension planes.

M16: slash + in-process hook ids.
M23: also skills, MCP connections, subagent YAML — merge into existing loaders.
"""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mini_claude_code.config import Settings, get_settings, resolve_workspace_root

logger = logging.getLogger(__name__)

PLUGIN_MANIFEST = "plugin.yaml"

# Seeded into workspace/plugins/ when missing (M16 review + M23 packs + M24).
_EXAMPLE_PACK_IDS = ("review", "docs-mcp", "research", "shell-hooks")


@dataclass
class PluginPack:
    """One plugin directory with a parsed manifest."""

    id: str
    name: str
    description: str
    slash_commands: dict[str, dict[str, Any]]
    hooks: dict[str, list[Any]]
    path: Path
    # M23: relative paths under ``path`` (skill dirs or SKILL.md files).
    skill_refs: list[str] = field(default_factory=list)
    # M23: server_name → raw connection dict (may use ``preset``).
    mcp: dict[str, dict[str, Any]] = field(default_factory=dict)
    # M23: relative paths to subagent YAML files.
    subagent_refs: list[str] = field(default_factory=list)


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
    hooks = _normalize_hook_section(hooks_raw, plugin_dir=path.parent.resolve())
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

    skill_refs = _parse_str_list(data.get("skills"), field_name="skills", path=path)
    subagent_refs = _parse_str_list(
        data.get("subagents"), field_name="subagents", path=path
    )
    mcp = _parse_mcp_section(data.get("mcp"), path=path)

    return PluginPack(
        id=plugin_id,
        name=name,
        description=description,
        slash_commands=slash_commands,
        hooks=hooks,
        path=path.parent.resolve(),
        skill_refs=skill_refs,
        mcp=mcp,
        subagent_refs=subagent_refs,
    )


def _parse_str_list(raw: Any, *, field_name: str, path: Path) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list in {path}")
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if not s:
            raise ValueError(f"{field_name} entries must be non-empty in {path}")
        out.append(s)
    return out


def _parse_mcp_section(raw: Any, *, path: Path) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"mcp must be a mapping in {path}")
    out: dict[str, dict[str, Any]] = {}
    for name, conn in raw.items():
        key = str(name).strip()
        if not key:
            raise ValueError(f"mcp server name must be non-empty in {path}")
        if not isinstance(conn, dict):
            raise ValueError(f"mcp.{key} must be an object in {path}")
        out[key] = dict(conn)
    return out


def _normalize_hook_section(
    hooks_raw: dict[str, Any],
    *,
    plugin_dir: Path | None = None,
) -> dict[str, list[Any]]:
    """Normalize hook lists: string ids or shell/script objects (M24)."""
    out: dict[str, list[Any]] = {
        "pre_tool_use": [],
        "post_tool_use": [],
        "stop": [],
    }
    for key in out:
        items = hooks_raw.get(key) or []
        if not isinstance(items, list):
            raise ValueError(f"hooks.{key} must be a list")
        normalized: list[Any] = []
        for item in items:
            if isinstance(item, str):
                normalized.append(item)
                continue
            if not isinstance(item, dict):
                raise ValueError(f"hooks.{key} entry must be string or mapping: {item!r}")
            if "id" in item and "type" not in item:
                normalized.append(str(item["id"]))
                continue
            typ = str(item.get("type") or "").strip().lower()
            if typ not in ("script", "shell"):
                raise ValueError(
                    f"hooks.{key} unknown type {typ!r} (expected script|shell or id)"
                )
            entry = dict(item)
            entry["type"] = typ
            if typ == "script":
                raw_path = entry.get("path")
                if not raw_path:
                    raise ValueError(f"hooks.{key} script requires path")
                p = Path(str(raw_path))
                if not p.is_absolute():
                    if plugin_dir is None:
                        raise ValueError(
                            f"hooks.{key} relative script path needs plugin dir"
                        )
                    p = (plugin_dir / p).resolve()
                    # jail
                    try:
                        p.relative_to(plugin_dir.resolve())
                    except ValueError as exc:
                        raise ValueError(
                            f"hooks.{key} script escapes plugin dir: {raw_path}"
                        ) from exc
                entry["path"] = str(p.resolve())
            normalized.append(entry)
        out[key] = normalized
    return out


def load_plugins_from_paths(paths: list[Path]) -> list[PluginPack]:
    return [load_plugin_manifest(p) for p in paths]


def ensure_example_plugins(workspace_root: Path) -> Path:
    """Seed package example packs into ``workspace/plugins/`` when missing."""
    root = workspace_root.expanduser().resolve() / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    examples = plugin_examples_dir()
    for pack_id in _EXAMPLE_PACK_IDS:
        src = examples / pack_id
        dest = root / pack_id
        if dest.exists() or not (src / PLUGIN_MANIFEST).is_file():
            continue
        shutil.copytree(src, dest)
        logger.info("Seeded example plugin pack %s → %s", pack_id, dest)
    return root


def discover_plugins(
    workspace_root: Path,
    *,
    extra_roots: list[Path] | None = None,
    seed_examples: bool = True,
) -> list[PluginPack]:
    """Scan ``workspace/plugins`` and optional extra roots (tests)."""
    if seed_examples:
        ensure_example_plugins(workspace_root)
    manifests: list[Path] = discover_plugin_manifests(workspace_root / "plugins")
    for root in extra_roots or []:
        manifests.extend(discover_plugin_manifests(root))
    return load_plugins_from_paths(manifests)


def resolve_plugins(
    settings: Settings | None = None,
    *,
    workspace_root: Path | None = None,
    extra_roots: list[Path] | None = None,
    seed_examples: bool = True,
) -> list[PluginPack]:
    settings = settings or get_settings()
    if not settings.plugins_enabled:
        return []
    root = workspace_root or resolve_workspace_root(settings)
    return discover_plugins(
        root, extra_roots=extra_roots, seed_examples=seed_examples
    )


def merge_hook_config_dicts(
    base: dict[str, Any] | None,
    plugins: list[PluginPack],
) -> dict[str, list[Any]]:
    """Append plugin hook entries after base; dedupe (first wins)."""
    merged: dict[str, list[Any]] = {
        "pre_tool_use": list((base or {}).get("pre_tool_use") or []),
        "post_tool_use": list((base or {}).get("post_tool_use") or []),
        "stop": list((base or {}).get("stop") or []),
    }
    for plugin in plugins:
        for key, value in merged.items():
            value.extend(plugin.hooks.get(key) or [])
    for key, value in merged.items():
        seen: set[str] = set()
        deduped: list[Any] = []
        for entry in value:
            token = _hook_entry_dedupe_key(entry)
            if token in seen:
                continue
            seen.add(token)
            deduped.append(entry)
        merged[key] = deduped
    return merged


def _hook_entry_dedupe_key(entry: Any) -> str:
    if isinstance(entry, str):
        return f"id:{entry}"
    if isinstance(entry, dict):
        if "type" in entry:
            typ = entry.get("type")
            if typ == "script":
                return f"script:{entry.get('path')}"
            return f"shell:{entry.get('command')}"
        if "id" in entry:
            return f"id:{entry['id']}"
    return repr(entry)


def _load_base_hooks_dict(
    settings: Settings,
    workspace_root: Path,
) -> dict[str, list[Any]] | None:
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
) -> dict[str, list[Any]] | None:
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


# --- M23: merge into skills / MCP / subagents planes ---


def _resolve_under_plugin(plugin: PluginPack, rel: str) -> Path:
    target = (plugin.path / rel).resolve()
    try:
        target.relative_to(plugin.path.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Plugin {plugin.id!r} path escapes pack dir: {rel!r}"
        ) from exc
    return target


def collect_plugin_skill_defs(plugins: list[PluginPack]) -> dict[str, Any]:
    """Load SkillDef from plugin skill_refs. Collision across plugins → error."""
    from mini_claude_code.agent.skills import SKILL_FILE_NAME, SkillDef, parse_skill_md

    found: dict[str, SkillDef] = {}
    for plugin in plugins:
        for rel in plugin.skill_refs:
            path = _resolve_under_plugin(plugin, rel)
            if path.is_dir():
                skill_md = path / SKILL_FILE_NAME
            else:
                skill_md = path
            if not skill_md.is_file():
                raise ValueError(
                    f"Plugin {plugin.id!r} skill not found: {rel} → {skill_md}"
                )
            defn = parse_skill_md(skill_md)
            if defn.name in found:
                raise ValueError(
                    f"Duplicate skill {defn.name!r} from plugins "
                    f"(also from {found[defn.name].path})"
                )
            found[defn.name] = defn
    return found


def materialize_mcp_connection(
    raw: dict[str, Any],
    *,
    plugin: PluginPack,
    server_name: str,
) -> dict[str, Any]:
    """Turn a plugin mcp entry into a MultiServerMCPClient connection dict."""
    from mini_claude_code.tools.mcp_loader import (
        default_demo_connections,
        fake_docs_connections,
    )

    if "preset" in raw:
        preset = str(raw["preset"]).strip()
        if preset == "fake_docs":
            return dict(fake_docs_connections()["fake_docs"])
        if preset == "echo_math":
            return dict(default_demo_connections()["echo_math"])
        raise ValueError(
            f"Plugin {plugin.id!r} mcp.{server_name} unknown preset {preset!r} "
            "(supported: fake_docs, echo_math)"
        )

    conn = dict(raw)
    cmd = conn.get("command")
    if cmd in ("python", "{python}", "PYTHON"):
        conn["command"] = sys.executable
    args = conn.get("args")
    if isinstance(args, list):
        resolved: list[str] = []
        for arg in args:
            s = str(arg)
            if s.startswith("{plugin}/"):
                resolved.append(str(_resolve_under_plugin(plugin, s[len("{plugin}/") :])))
            elif s.startswith("./") or (
                not s.startswith("/") and (plugin.path / s).exists()
            ):
                resolved.append(str(_resolve_under_plugin(plugin, s)))
            else:
                resolved.append(s)
        conn["args"] = resolved
    return conn


def collect_plugin_mcp_connections(
    plugins: list[PluginPack],
) -> dict[str, dict[str, Any]]:
    """Materialize MCP connections from plugins. Duplicate server name → error."""
    out: dict[str, dict[str, Any]] = {}
    owners: dict[str, str] = {}
    for plugin in plugins:
        for server_name, raw in plugin.mcp.items():
            if server_name in out:
                raise ValueError(
                    f"Duplicate MCP server {server_name!r} "
                    f"(plugins {owners[server_name]!r} and {plugin.id!r})"
                )
            out[server_name] = materialize_mcp_connection(
                raw, plugin=plugin, server_name=server_name
            )
            owners[server_name] = plugin.id
    return out


def merge_mcp_connections(
    base: dict[str, dict[str, Any]],
    plugins: list[PluginPack],
) -> dict[str, dict[str, Any]]:
    """Union base settings MCP with plugin MCP; collision → error."""
    plugin_conns = collect_plugin_mcp_connections(plugins)
    merged = dict(base)
    for name, conn in plugin_conns.items():
        if name in merged:
            raise ValueError(
                f"Duplicate MCP server {name!r}: already in settings/config "
                f"and also declared by a plugin"
            )
        merged[name] = conn
    return merged


def collect_plugin_subagent_defs(plugins: list[PluginPack]) -> dict[str, Any]:
    """Load SubAgentDef from plugin refs. Collision across plugins → error."""
    from mini_claude_code.agent.subagents import SubAgentDef, load_subagent_def

    found: dict[str, SubAgentDef] = {}
    for plugin in plugins:
        for rel in plugin.subagent_refs:
            path = _resolve_under_plugin(plugin, rel)
            if not path.is_file():
                raise ValueError(
                    f"Plugin {plugin.id!r} subagent not found: {rel} → {path}"
                )
            defn = load_subagent_def(path)
            if defn.name in found:
                raise ValueError(
                    f"Duplicate subagent {defn.name!r} from plugins "
                    f"(also from {found[defn.name].path})"
                )
            found[defn.name] = defn
    return found
