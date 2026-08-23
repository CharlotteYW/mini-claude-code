"""Minimal ReAct agent as a LangGraph StateGraph (M2+).

M3: default tools are workspace filesystem tools (path-jailed). Pass `tools=`
to inject demos/fakes in tests. Topology stays call_model ↔ tools.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.config import Settings, get_settings, resolve_workspace_root
from mini_claude_code.llm import create_chat_model
from mini_claude_code.tools import build_coding_tools

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
    checkpointer: MemorySaver | None = None,
) -> CompiledStateGraph:
    """Compile call_model ↔ tools ReAct graph.

    Pass `llm` / `tools` to inject fakes in unit tests (no network).
    Pass `checkpointer=MemorySaver()` for in-process multi-turn demos only —
    durable Postgres checkpointing is M5.
    """
    settings = settings or get_settings()
    model = llm or create_chat_model(settings)
    tool_list: list[BaseTool] = (
        list(tools)
        if tools is not None
        else build_coding_tools(resolve_workspace_root(settings))
    )
    bound = model.bind_tools(tool_list)

    def call_model(state: MessagesState) -> dict[str, list[Any]]:
        response = bound.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", ToolNode(tool_list))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", route_after_model)
    graph.add_edge("tools", "call_model")

    return graph.compile(checkpointer=checkpointer)
