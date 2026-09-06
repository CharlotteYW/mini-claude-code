"""Skills with progressive disclosure (M13).

L0: name + description catalog injected every model turn.
L1: ``load_skill(name)`` returns the full body (ToolMessage); we also re-inject
loaded bodies into the prompt view by scanning prior ToolMessages.

Skills enrich *this* agent’s context. Sub-agents (M12) spawn an isolated child graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

SKILL_FILE_NAME = "SKILL.md"
CATALOG_MARKER = "[skills catalog]"
LOADED_MARKER = "[loaded skills]"


@dataclass(frozen=True)
class SkillDef:
    name: str
    description: str
    body: str
    path: Path


def skills_dir(workspace_root: Path) -> Path:
    return workspace_root.expanduser().resolve() / "skills"


def ensure_example_skills(workspace_root: Path) -> Path:
    """Create skills/ and seed workspace-layout from the package example if missing."""
    root = skills_dir(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    target_dir = root / "workspace-layout"
    target = target_dir / SKILL_FILE_NAME
    if not target.is_file():
        packaged = (
            Path(__file__).resolve().parent / "skill_examples" / "workspace-layout" / SKILL_FILE_NAME
        )
        if packaged.is_file():
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(packaged.read_text(encoding="utf-8"), encoding="utf-8")
    return root


def parse_skill_md(path: Path) -> SkillDef:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"SKILL.md must start with YAML frontmatter: {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"SKILL.md frontmatter not closed: {path}")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    if not isinstance(meta, dict):
        raise ValueError(f"skill frontmatter must be a mapping: {path}")
    name = str(meta.get("name") or path.parent.name).strip()
    description = str(meta.get("description") or "").strip()
    if not name:
        raise ValueError(f"skill name required: {path}")
    if not description:
        raise ValueError(f"skill description required: {path}")
    if not body:
        raise ValueError(f"skill body required: {path}")
    return SkillDef(name=name, description=description, body=body, path=path)


def load_skill_defs(
    workspace_root: Path,
    *,
    extra: dict[str, SkillDef] | None = None,
) -> dict[str, SkillDef]:
    """Load ``skills/*/SKILL.md`` plus optional plugin extras (M23).

    Name collision between workspace and ``extra`` → ValueError (fail closed).
    """
    root = ensure_example_skills(workspace_root)
    found: dict[str, SkillDef] = {}
    for skill_md in sorted(root.glob(f"*/{SKILL_FILE_NAME}")):
        defn = parse_skill_md(skill_md)
        found[defn.name] = defn
    for name, defn in (extra or {}).items():
        if name in found:
            raise ValueError(
                f"Duplicate skill {name!r}: workspace {found[name].path} "
                f"vs plugin asset {defn.path}"
            )
        found[name] = defn
    return found


def format_skills_catalog(defs: dict[str, SkillDef]) -> str:
    """L0: names + descriptions only — no bodies."""
    if not defs:
        return f"{CATALOG_MARKER}\n(no skills installed under workspace/skills/)"
    lines = [
        CATALOG_MARKER,
        "Available skills (use load_skill(name) to load full instructions):",
    ]
    for name in sorted(defs):
        lines.append(f"- {name}: {defs[name].description}")
    return "\n".join(lines)


def collect_loaded_skill_bodies(messages: list[BaseMessage]) -> dict[str, str]:
    """Recover L1 bodies from prior load_skill ToolMessages in the transcript."""
    loaded: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.name != "load_skill":
            continue
        content = str(message.content or "")
        # Convention from load_skill return format.
        header = re.match(
            r"\[skill:([^\]]+)\]\n(.*)\Z",
            content,
            re.DOTALL,
        )
        if header:
            loaded[header.group(1).strip()] = header.group(2).strip()
    return loaded


def inject_skills_view(
    messages: list[BaseMessage],
    workspace_root: Path,
    *,
    extra_skills: dict[str, SkillDef] | None = None,
) -> list[BaseMessage]:
    """Prepend catalog (L0) and any loaded skill bodies (L1) for the prompt view."""
    defs = load_skill_defs(workspace_root, extra=extra_skills)
    catalog = format_skills_catalog(defs)
    loaded = collect_loaded_skill_bodies(messages)

    out = list(messages)
    # Avoid stacking duplicate catalog/loaded blocks on tool-loop iterations.
    has_catalog = any(
        isinstance(m, SystemMessage) and CATALOG_MARKER in str(m.content)
        for m in out[:4]
    )
    has_loaded = any(
        isinstance(m, SystemMessage) and LOADED_MARKER in str(m.content)
        for m in out[:4]
    )

    prefix: list[BaseMessage] = []
    if loaded and not has_loaded:
        parts = [LOADED_MARKER]
        for name, body in sorted(loaded.items()):
            parts.append(f"## skill:{name}\n{body}")
        prefix.append(SystemMessage(content="\n\n".join(parts)))
    if not has_catalog:
        prefix.append(SystemMessage(content=catalog))
    return [*prefix, *out] if prefix else out


def build_skill_tools(
    workspace_root: Path,
    *,
    extra_skills: dict[str, SkillDef] | None = None,
) -> list[BaseTool]:
    """Parent tool ``load_skill`` (L1 activation)."""
    root = workspace_root.expanduser().resolve()
    defs = load_skill_defs(root, extra=extra_skills)
    available = ", ".join(sorted(defs)) or "(none)"

    def load_skill(name: str) -> str:
        """Load the full body of a named skill into this conversation.

        Prefer this when the skills catalog lists a relevant playbook.
        Does not start a sub-agent — instructions apply to the current agent.
        """
        if not name or not name.strip():
            return "ERROR: skill name must be non-empty"
        key = name.strip()
        # Reload defs so new files / plugin packs appear without rebuilding.
        current = load_skill_defs(root, extra=extra_skills)
        defn = current.get(key)
        if defn is None:
            return f"ERROR: unknown skill {key!r}. Available: {', '.join(sorted(current)) or '(none)'}"
        return f"[skill:{defn.name}]\n{defn.body}"

    return [
        StructuredTool.from_function(
            load_skill,
            name="load_skill",
            description=(
                "Load full instructions for a skill by name (progressive disclosure). "
                f"Available: {available}. "
                "Use after seeing the skills catalog; not a sub-agent."
            ),
        )
    ]
