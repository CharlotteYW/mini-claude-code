"""Slash commands (M16): expand plugin templates; /help and /plugins discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mini_claude_code.agent.plugins import PluginPack, build_slash_registry

META_SLASH_COMMANDS = frozenset({"help", "plugins"})


@dataclass
class SlashDispatch:
    """Result of parsing user slash input at the CLI boundary."""

    kind: Literal["invoke", "list", "not_slash"]
    prompt: str = ""
    list_text: str = ""


def parse_slash_parts(text: str) -> tuple[str, str] | None:
    """Return (command, args) if text is a slash command, else None."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    body = stripped[1:].strip()
    if not body:
        return "", ""
    parts = body.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args


def expand_template(template: str, args: str) -> str:
    """Substitute ``{{args}}`` or append trailing user args."""
    if "{{args}}" in template:
        return template.replace("{{args}}", args)
    text = template.rstrip()
    if args:
        return f"{text}\n\n{args}"
    return text


def format_slash_list(
    registry: dict[str, dict[str, str]],
    *,
    plugins: list[PluginPack] | None = None,
) -> str:
    """Human-readable catalog for /help and /plugins."""
    lines = ["Slash commands (from plugins):"]
    if plugins:
        lines.append("")
        lines.append("Installed plugin packs:")
        for pack in plugins:
            desc = pack.description or "(no description)"
            planes: list[str] = []
            if pack.slash_commands:
                planes.append(f"slash={len(pack.slash_commands)}")
            if any(pack.hooks.values()):
                planes.append("hooks")
            if pack.skill_refs:
                planes.append(f"skills={len(pack.skill_refs)}")
            if pack.mcp:
                planes.append(f"mcp={len(pack.mcp)}")
            if pack.subagent_refs:
                planes.append(f"subagents={len(pack.subagent_refs)}")
            plane_s = ", ".join(planes) if planes else "empty"
            lines.append(f"  {pack.id}: {pack.name} — {desc} [{plane_s}]")
        lines.append("")
    if not registry:
        lines.append("  (none — add workspace/plugins/*/plugin.yaml)")
    else:
        for name in sorted(registry):
            entry = registry[name]
            desc = entry.get("description") or "(no description)"
            pid = entry.get("plugin_id") or "?"
            lines.append(f"  /{name}  — {desc} (plugin: {pid})")
    lines.append("")
    lines.append("Type a command to run it, e.g. /review")
    lines.append("Meta: /help, /plugins (this list; does not invoke the agent)")
    return "\n".join(lines)


def dispatch_slash_input(
    text: str,
    registry: dict[str, dict[str, str]],
    *,
    plugins: list[PluginPack] | None = None,
) -> SlashDispatch:
    """Parse user line; expand slash or return list meta-command."""
    parts = parse_slash_parts(text)
    if parts is None:
        return SlashDispatch(kind="not_slash", prompt=text)
    command, args = parts
    if command in META_SLASH_COMMANDS:
        return SlashDispatch(
            kind="list",
            list_text=format_slash_list(registry, plugins=plugins),
        )
    if not command:
        return SlashDispatch(
            kind="list",
            list_text=format_slash_list(registry, plugins=plugins),
        )
    if command not in registry:
        known = ", ".join(f"/{n}" for n in sorted(registry)) or "(none)"
        raise ValueError(
            f"Unknown slash command /{command}. Known: {known}. Try /help."
        )
    entry = registry[command]
    expanded = expand_template(entry["template"], args)
    return SlashDispatch(kind="invoke", prompt=expanded)


def slash_registry_from_plugins(plugins: list[PluginPack]) -> dict[str, dict[str, str]]:
    return build_slash_registry(plugins)
