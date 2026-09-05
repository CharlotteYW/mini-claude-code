"""Sub-agent definitions (YAML) and delegation tool (M12).

Parent binds ``run_subagent``; the tool body compiles a *child* ReAct graph with
a fresh message list and an allowlisted tool set — isolated context, same model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.git_tools import build_git_tools
from mini_claude_code.tools.memory_tools import build_memory_tools
from mini_claude_code.tools.shell import build_shell_tools

# Prevent infinite parent↔child delegation.
_FORBIDDEN_CHILD_TOOLS = frozenset({"run_subagent"})


@dataclass(frozen=True)
class SubAgentDef:
    name: str
    description: str
    tools: tuple[str, ...]
    system: str
    path: Path


def subagents_dir(workspace_root: Path) -> Path:
    return workspace_root.expanduser().resolve() / "subagents"


def ensure_example_subagents(workspace_root: Path) -> Path:
    """Create ``subagents/`` and seed explore.yaml from the package example if missing."""
    root = subagents_dir(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "explore.yaml"
    if not target.is_file():
        packaged = (
            Path(__file__).resolve().parent / "subagent_examples" / "explore.yaml"
        )
        if packaged.is_file():
            target.write_text(packaged.read_text(encoding="utf-8"), encoding="utf-8")
    return root


def load_subagent_def(path: Path) -> SubAgentDef:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"subagent file must be a mapping: {path}")
    name = str(data.get("name") or path.stem).strip()
    description = str(data.get("description") or "").strip()
    system = str(data.get("system") or "").strip()
    tools_raw = data.get("tools") or []
    if not isinstance(tools_raw, list):
        raise ValueError(f"subagent tools must be a list: {path}")
    tools = tuple(str(t).strip() for t in tools_raw if str(t).strip())
    if not name:
        raise ValueError(f"subagent name required: {path}")
    if not description:
        raise ValueError(f"subagent description required: {path}")
    return SubAgentDef(
        name=name,
        description=description,
        tools=tools,
        system=system,
        path=path,
    )


def load_subagent_defs(workspace_root: Path) -> dict[str, SubAgentDef]:
    """Load ``*.yaml`` / ``*.yml`` from workspace/subagents/."""
    root = ensure_example_subagents(workspace_root)
    found: dict[str, SubAgentDef] = {}
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        defn = load_subagent_def(path)
        found[defn.name] = defn
    return found


def build_tool_catalog(
    workspace_root: Path,
    settings: Settings,
) -> dict[str, BaseTool]:
    """All tools a subagent might allowlist (excludes run_subagent)."""
    root = workspace_root.expanduser().resolve()
    tools = [
        *build_coding_tools(root),
        *build_shell_tools(
            root,
            timeout_sec=settings.shell_timeout_sec,
            backend=settings.shell_backend,  # type: ignore[arg-type]
            docker_image=settings.shell_docker_image,
            docker_network=settings.shell_docker_network,
        ),
        *build_git_tools(root),
        *build_memory_tools(settings, workspace_root=root),
    ]
    return {t.name: t for t in tools if t.name not in _FORBIDDEN_CHILD_TOOLS}


def tools_for_allowlist(
    catalog: dict[str, BaseTool],
    allowlist: Sequence[str],
) -> list[BaseTool]:
    selected: list[BaseTool] = []
    missing: list[str] = []
    for name in allowlist:
        if name in _FORBIDDEN_CHILD_TOOLS:
            continue
        tool = catalog.get(name)
        if tool is None:
            missing.append(name)
        else:
            selected.append(tool)
    if missing:
        raise ValueError(
            "unknown subagent tools (not in catalog): " + ", ".join(missing)
        )
    return selected


def _last_ai_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            text = message.content
            if isinstance(text, str) and text.strip():
                return text.strip()
    return "(subagent finished with no assistant text)"


def build_subagent_tools(
    workspace_root: Path,
    *,
    settings: Settings | None = None,
    llm: BaseChatModel | None = None,
    plan_mode: bool = False,
) -> list[BaseTool]:
    """Parent-facing ``run_subagent`` tool (loads YAML defs from workspace)."""
    settings = settings or get_settings()
    root = workspace_root.expanduser().resolve()
    defs = load_subagent_defs(root)
    catalog = build_tool_catalog(root, settings)
    available = ", ".join(sorted(defs)) or "(none)"

    def run_subagent(name: str, task: str) -> str:
        """Delegate a task to a named sub-agent with isolated context.

        The child does not see the parent transcript — only ``task`` plus its
        own system brief and allowlisted tools. Same model as the parent.
        """
        if not name or not name.strip():
            return "ERROR: subagent name must be non-empty"
        if not task or not task.strip():
            return "ERROR: task must be non-empty"
        key = name.strip()
        defn = defs.get(key)
        if defn is None:
            return f"ERROR: unknown subagent {key!r}. Available: {available}"

        try:
            child_tools = tools_for_allowlist(catalog, defn.tools)
        except ValueError as exc:
            return f"ERROR: {exc}"

        # Lazy import avoids circular import with graph → default tools.
        from mini_claude_code.agent.graph import build_agent_graph

        child = build_agent_graph(
            settings=settings,
            llm=llm,
            tools=child_tools,
            checkpointer=None,
            plan_mode=plan_mode,
            # Child HITL simplification: no stdin/interrupt nesting — deny asks.
            ask_callback=lambda _n, _a: False,
            apply_tool_permissions=True,
        )
        messages: list[Any] = []
        if defn.system:
            messages.append(SystemMessage(content=defn.system))
        messages.append(HumanMessage(content=task.strip()))
        try:
            result = child.invoke(
                {"messages": messages},
                config={"recursion_limit": 10},
            )
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: subagent {key!r} failed: {exc}"

        summary = _last_ai_text(list(result.get("messages") or []))
        return f"[subagent:{key}]\n{summary}"

    desc = (
        "Run a named sub-agent with an isolated context and tool allowlist. "
        f"Available subagents: {available}. "
        "Pass the subagent name and a clear task; receive a text summary."
    )
    return [
        StructuredTool.from_function(
            run_subagent,
            name="run_subagent",
            description=desc,
        )
    ]
