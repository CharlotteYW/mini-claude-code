"""Eval case runner — outside the agent graph."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage

from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.config import Settings, get_settings, repo_root
from mini_claude_code.eval.cases import EvalCase, check_assertion, load_eval_case
from mini_claude_code.eval.fake_llm import ScriptedFakeLLM
from mini_claude_code.tools import build_coding_tools, demo_tools


@dataclass
class EvalResult:
    name: str
    passed: bool
    skipped: bool = False
    reason: str = ""


def default_cases_dir() -> Path:
    return (repo_root() / "backend" / "evals" / "cases").resolve()


def _resolve_tools(case: EvalCase, workspace: Path):
    if case.toolset == "demo":
        return demo_tools()
    if case.toolset == "coding":
        return build_coding_tools(workspace)
    raise ValueError(f"unknown toolset: {case.toolset!r}")


def _eval_settings(workspace: Path) -> Settings:
    """Isolated settings: no plugins/hooks/MCP noise; compaction off for determinism."""
    os.environ["WORKSPACE_ROOT"] = str(workspace)
    os.environ["PLUGINS_ENABLED"] = "0"
    os.environ["HOOKS_USE_DEMO"] = "0"
    os.environ["MCP_USE_DEMO"] = "0"
    os.environ["CONTEXT_COMPACT_THRESHOLD"] = "0"
    get_settings.cache_clear()
    return get_settings()


def run_eval_case(
    case: EvalCase,
    *,
    workspace: Path,
    settings: Settings | None = None,
) -> EvalResult:
    settings = settings or _eval_settings(workspace)

    if case.live:
        return EvalResult(
            name=case.name,
            passed=False,
            skipped=True,
            reason="live case (run via integration test with provider)",
        )

    if not case.fake_steps:
        return EvalResult(
            name=case.name,
            passed=False,
            skipped=False,
            reason="non-live case requires fake_llm.steps",
        )

    tools = _resolve_tools(case, workspace)
    graph = build_agent_graph(
        settings=settings,
        llm=ScriptedFakeLLM(case.fake_steps),
        tools=tools,
        plan_mode=case.plan_mode,
        apply_tool_hooks=False,
        ask_callback=None,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content=case.prompt)]},
        config={"recursion_limit": DEFAULT_RECURSION_LIMIT},
    )
    messages = result.get("messages") or []
    for assertion in case.assertions:
        check_assertion(assertion, messages)
    return EvalResult(name=case.name, passed=True)


def run_case_file(path: Path, *, workspace: Path) -> EvalResult:
    case = load_eval_case(path)
    try:
        return run_eval_case(case, workspace=workspace)
    except Exception as exc:  # noqa: BLE001
        return EvalResult(name=case.name, passed=False, reason=str(exc))


def run_all_cases(
    cases_dir: Path | None = None,
    *,
    workspace: Path,
) -> list[EvalResult]:
    root = cases_dir or default_cases_dir()
    paths = sorted(root.glob("*.yaml"))
    if not paths:
        raise FileNotFoundError(f"no eval cases in {root}")
    return [run_case_file(p, workspace=workspace) for p in paths]
