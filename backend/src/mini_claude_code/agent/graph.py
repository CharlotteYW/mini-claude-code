"""Minimal ReAct agent as a LangGraph StateGraph (M2+).

Default tools: workspace FS (M3) + shell/git (M4) + Neo4j memory (M8).
Topology stays call_model ↔ tools. Shell defaults to Docker sandbox (M11);
host subprocess remains an opt-in backend.

Streaming (M6): pass RunnableConfig into `bound.invoke(..., config)`.
Compaction (M7) then project/fact inject (M8) before invoke (policy plane).
Permissions / Plan Mode (M9) wrap tools before ToolNode — not new graph nodes.
Ask uses LangGraph interrupt (M10); resume with Command(resume=bool).
Sub-agents (M12): ``run_subagent`` tool nests a child graph with isolated messages.
Skills (M13): catalog inject + ``load_skill`` progressive disclosure.
MCP (M14): optional adapter tools merged into the same ToolNode (opt-in config).
Hooks (M15): Pre/Post around tools; Stop on final model message without tool_calls.
Plugins (M16/M23): slash + hook merge; packs also contribute skills/MCP/subagents.
Retry/usage (M17): transient LLM retry at invoke; optional token accounting footer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from mini_claude_code.agent.compact import default_summarizer, maybe_compact_messages
from mini_claude_code.agent.hooks import (
    HookRegistry,
    apply_hooks,
    resolve_hook_registry,
    run_stop_hooks,
)
from mini_claude_code.agent.permissions import AskCallback, apply_permissions
from mini_claude_code.agent.project_memory import inject_project_memory
from mini_claude_code.agent.retry import invoke_with_retry
from mini_claude_code.agent.skills import inject_skills_view
from mini_claude_code.agent.usage import (
    UsageAccumulator,
    get_usage_accumulator,
    record_llm_usage,
)
from mini_claude_code.config import Settings, get_settings, resolve_workspace_root
from mini_claude_code.llm import create_chat_model
from mini_claude_code.memory.neo4j_facts import recall_facts_block
from mini_claude_code.tools import build_default_tools

# Safe default for a toy ReAct loop (model → tools → model → …).
DEFAULT_RECURSION_LIMIT = 10


def route_after_model(state: MessagesState) -> Literal["tools", "__end__"]:
    """Branch on normalized tool_calls — same signal M1 taught us to trust."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def _inject_memory_view(
    messages: list[Any],
    *,
    workspace_root,
    settings: Settings,
) -> list[Any]:
    """compact → AGENT.md → skills catalog/loaded → optional Neo4j facts."""
    from mini_claude_code.agent.plugins import (
        collect_plugin_skill_defs,
        resolve_plugins,
    )

    view = inject_project_memory(list(messages), workspace_root, ensure=True)
    plugins = resolve_plugins(settings, workspace_root=workspace_root)
    extra_skills = collect_plugin_skill_defs(plugins) if plugins else None
    view = inject_skills_view(view, workspace_root, extra_skills=extra_skills)
    facts_block = recall_facts_block(limit=8, settings=settings)
    if not facts_block:
        return view
    marker = "[durable facts from Neo4j]"
    # Avoid stacking duplicate fact blocks across tool-loop iterations.
    if any(
        isinstance(m, SystemMessage) and marker in str(m.content) for m in view[:5]
    ):
        return view
    return [SystemMessage(content=facts_block), *view]


def build_agent_graph(
    *,
    settings: Settings | None = None,
    llm: BaseChatModel | None = None,
    tools: Sequence[BaseTool] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    plan_mode: bool | None = None,
    ask_callback: AskCallback | None = None,
    apply_tool_permissions: bool = True,
    hook_registry: HookRegistry | None = None,
    apply_tool_hooks: bool = True,
    usage_accumulator: UsageAccumulator | None = None,
) -> CompiledStateGraph:
    """Compile call_model ↔ tools ReAct graph.

    Pass `llm` / `tools` to inject fakes in unit tests (no network).
    Pass a checkpointer (MemorySaver or PostgresSaver) for multi-turn sessions.
    Pass ``store`` (M30) for cross-thread KV tools + ``compile(store=…)``.
    `plan_mode` defaults to Settings.agent_plan_mode. Set
    `apply_tool_permissions=False` only for low-level tests that need bare tools.

    Tool wrap order: **permissions first (inner), hooks outer** so runtime is
    Pre → permissions/HITL → body → Post.
    """
    settings = settings or get_settings()
    model = llm or create_chat_model(settings)
    workspace = resolve_workspace_root(settings)
    effective_plan = (
        settings.agent_plan_mode if plan_mode is None else plan_mode
    )
    tool_list: list[BaseTool] = (
        list(tools)
        if tools is not None
        else build_default_tools(
            workspace,
            shell_timeout_sec=settings.shell_timeout_sec,
            settings=settings,
            llm=model,
            plan_mode=effective_plan,
            store=store,
        )
    )
    if apply_tool_permissions:
        tool_list = apply_permissions(
            tool_list,
            plan_mode=effective_plan,
            ask_callback=ask_callback,
        )
    registry = (
        hook_registry
        if hook_registry is not None
        else resolve_hook_registry(settings, workspace_root=workspace)
    )
    if apply_tool_hooks:
        tool_list = apply_hooks(tool_list, registry)
    bound = model.bind_tools(tool_list)

    def _record_usage(response: Any, config: RunnableConfig) -> None:
        record_llm_usage(
            response,
            config,
            fallback=usage_accumulator or get_usage_accumulator(config),
        )

    summarizer = default_summarizer(
        model,
        settings=settings,
        on_response=lambda msg: record_llm_usage(
            msg, None, fallback=usage_accumulator
        ),
    )

    def call_model(
        state: MessagesState, config: RunnableConfig
    ) -> dict[str, list[Any]]:
        messages = list(state["messages"])
        compacted, did_compact = maybe_compact_messages(
            messages,
            threshold_tokens=settings.context_compact_threshold,
            keep_recent=settings.context_keep_recent,
            summarizer=summarizer,
        )
        # Prompt view: inject project + facts without necessarily rewriting state
        # unless compaction already rewrote the transcript.
        prompt_messages = _inject_memory_view(
            compacted, workspace_root=workspace, settings=settings
        )
        # Keep call_model sync so graph.invoke (tests / --sync) still works.
        # M22 async win is ToolNode → tool.ainvoke (permission/hook coroutines).
        response = invoke_with_retry(
            lambda: bound.invoke(prompt_messages, config),
            settings=settings,
        )
        _record_usage(response, config)
        # Stop hooks: turn ended without further tool_calls (best-effort).
        if (
            apply_tool_hooks
            and isinstance(response, AIMessage)
            and not response.tool_calls
        ):
            content = response.content
            text = content if isinstance(content, str) else str(content)
            run_stop_hooks(registry, content=text)
        if did_compact:
            return {
                "messages": [
                    RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    *compacted,
                    response,
                ]
            }
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode(tool_list))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", route_after_model)
    graph.add_edge("tools", "call_model")

    return graph.compile(checkpointer=checkpointer, store=store)
