"""Minimal ReAct agent as a LangGraph StateGraph (M2+).

Default tools: workspace FS (M3) + shell/git (M4) + Neo4j memory (M8).
Topology stays call_model ↔ tools. Shell is host subprocess until M11 sandbox.

Streaming (M6): pass RunnableConfig into `bound.invoke(..., config)`.
Compaction (M7) then project/fact inject (M8) before invoke (policy plane).
"""

from __future__ import annotations

from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.agent.compact import default_summarizer, maybe_compact_messages
from mini_claude_code.agent.project_memory import inject_project_memory
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
    """compact → AGENT.md → optional Neo4j fact block (prompt view only)."""
    view = inject_project_memory(list(messages), workspace_root, ensure=True)
    facts_block = recall_facts_block(limit=8, settings=settings)
    if not facts_block:
        return view
    marker = "[durable facts from Neo4j]"
    # Avoid stacking duplicate fact blocks across tool-loop iterations.
    if any(
        isinstance(m, SystemMessage) and marker in str(m.content) for m in view[:3]
    ):
        return view
    return [SystemMessage(content=facts_block), *view]


def build_agent_graph(
    *,
    settings: Settings | None = None,
    llm: BaseChatModel | None = None,
    tools: Sequence[BaseTool] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Compile call_model ↔ tools ReAct graph.

    Pass `llm` / `tools` to inject fakes in unit tests (no network).
    Pass a checkpointer (MemorySaver or PostgresSaver) for multi-turn sessions.
    """
    settings = settings or get_settings()
    model = llm or create_chat_model(settings)
    workspace = resolve_workspace_root(settings)
    tool_list: list[BaseTool] = (
        list(tools)
        if tools is not None
        else build_default_tools(
            workspace,
            shell_timeout_sec=settings.shell_timeout_sec,
            settings=settings,
        )
    )
    bound = model.bind_tools(tool_list)
    summarizer = default_summarizer(model)

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
        response = bound.invoke(prompt_messages, config)
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

    return graph.compile(checkpointer=checkpointer)
