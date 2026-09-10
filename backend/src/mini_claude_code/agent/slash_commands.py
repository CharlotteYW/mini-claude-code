"""Slash commands (M16/M24): expand plugin templates; /help, /plugins, /pick."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from mini_claude_code.agent.plugins import PluginPack, build_slash_registry

META_SLASH_COMMANDS = frozenset({"help", "plugins"})
PICK_SLASH_COMMANDS = frozenset({"pick"})


@dataclass
class SlashDispatch:
    """Result of parsing user slash input at the CLI boundary."""

    kind: Literal["invoke", "list", "pick", "not_slash"]
    prompt: str = ""
    list_text: str = ""
    # Ordered (command_name, description) for numbered picker.
    pick_choices: list[tuple[str, str]] = field(default_factory=list)


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
    lines.append("Meta: /help, /plugins (list); /pick (numbered picker)")
    lines.append("REPL time-travel: /rewind [index|checkpoint_id] (M31)")
    return "\n".join(lines)


def pick_choices_from_registry(
    registry: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    """Stable numbered order for /pick."""
    out: list[tuple[str, str]] = []
    for name in sorted(registry):
        desc = registry[name].get("description") or "(no description)"
        out.append((name, desc))
    return out


def format_pick_list(choices: list[tuple[str, str]]) -> str:
    lines = ["Pick a slash command (enter number):"]
    if not choices:
        lines.append("  (none — add workspace/plugins/*/plugin.yaml)")
        return "\n".join(lines)
    for i, (name, desc) in enumerate(choices, start=1):
        lines.append(f"  {i}. /{name}  — {desc}")
    lines.append("")
    lines.append("Or type /help for the full list.")
    return "\n".join(lines)


def resolve_pick_selection(
    registry: dict[str, dict[str, str]],
    selection: str,
    *,
    args: str = "",
) -> str:
    """Map a number (or command name) to an expanded prompt."""
    choices = pick_choices_from_registry(registry)
    if not choices:
        raise ValueError("No slash commands available to pick")
    raw = selection.strip()
    if not raw:
        raise ValueError("Empty pick selection")
    if raw.isdigit():
        idx = int(raw)
        if idx < 1 or idx > len(choices):
            raise ValueError(f"Pick number out of range 1..{len(choices)}")
        name = choices[idx - 1][0]
    else:
        name = raw.lstrip("/").lower()
        if name not in registry:
            raise ValueError(f"Unknown pick target {raw!r}")
    entry = registry[name]
    return expand_template(entry["template"], args)


def dispatch_slash_input(
    text: str,
    registry: dict[str, dict[str, str]],
    *,
    plugins: list[PluginPack] | None = None,
) -> SlashDispatch:
    """Parse user line; expand slash or return list/pick meta-command."""
    parts = parse_slash_parts(text)
    if parts is None:
        return SlashDispatch(kind="not_slash", prompt=text)
    command, args = parts
    if command in META_SLASH_COMMANDS:
        return SlashDispatch(
            kind="list",
            list_text=format_slash_list(registry, plugins=plugins),
        )
    if command in PICK_SLASH_COMMANDS or command == "":
        # Empty `/` and `/pick` → numbered picker (M24). `/` alone also lists via pick.
        choices = pick_choices_from_registry(registry)
        return SlashDispatch(
            kind="pick",
            list_text=format_pick_list(choices),
            pick_choices=choices,
            prompt=args,  # optional trailing args applied after pick
        )
    if command not in registry:
        known = ", ".join(f"/{n}" for n in sorted(registry)) or "(none)"
        raise ValueError(
            f"Unknown slash command /{command}. Known: {known}. Try /help or /pick."
        )
    entry = registry[command]
    expanded = expand_template(entry["template"], args)
    return SlashDispatch(kind="invoke", prompt=expanded)


def slash_registry_from_plugins(plugins: list[PluginPack]) -> dict[str, dict[str, str]]:
    return build_slash_registry(plugins)
