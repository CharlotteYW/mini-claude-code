"""Minimal ReAct agent as a LangGraph StateGraph (M2+).

Default tools: workspace FS (M3) + shell/git (M4). Pass `tools=` for tests.
Topology stays call_model ↔ tools. Shell is host subprocess until M11 sandbox.

Streaming (M6): pass RunnableConfig into `bound.invoke(..., config)` so
`graph.stream(stream_mode=\"messages\")` receives LLM tokens via callbacks.
Manual `model.stream()` loops are unnecessary for token UX and easy to get wrong.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.config import Settings, get_settings, resolve_workspace_root
from mini_claude_code.llm import create_chat_model
from mini_claude_code.tools import build_default_tools

# Safe default for a toy ReAct loop (model → tools → model → …).
DEFAULT_RECURSION_LIMIT = 10


def route_after_model(state: MessagesState) -> Literal["tools", "__end__"]:
    """Branch on normalized tool_calls — same signal M1 taught us to trust."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


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
    tool_list: list[BaseTool] = (
        list(tools)
        if tools is not None
        else build_default_tools(
            resolve_workspace_root(settings),
            shell_timeout_sec=settings.shell_timeout_sec,
        )
    )
    bound = model.bind_tools(tool_list)

    def call_model(
        state: MessagesState, config: RunnableConfig
    ) -> dict[str, list[Any]]:
        # Passing config is what enables stream_mode="messages" token events.
        response = bound.invoke(state["messages"], config)
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode(tool_list))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", route_after_model)
    graph.add_edge("tools", "call_model")

    return graph.compile(checkpointer=checkpointer)
