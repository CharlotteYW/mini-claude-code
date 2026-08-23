"""Minimal ReAct agent as a LangGraph StateGraph (M2).

Why a graph instead of `while True`:
- Conditional edges make the tool/no-tool branch explicit and testable.
- Later milestones attach checkpointer (M5), interrupt (M10), streaming (M6),
  and subgraphs (M12) to *this* runtime — not to an ad-hoc Python loop.

Option B: this graph is the thin cognition core only. Permissions / hooks /
sandbox stay outside until their milestones.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from mini_claude_code.config import Settings, get_settings
from mini_claude_code.llm import create_chat_model
from mini_claude_code.tools import demo_tools

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
    checkpointer: MemorySaver | None = None,
) -> CompiledStateGraph:
    """Compile call_model ↔ tools ReAct graph.

    Pass `llm` to inject a fake model in unit tests (no network).
    Pass `checkpointer=MemorySaver()` for in-process multi-turn demos only —
    durable Postgres checkpointing is M5.
    """
    settings = settings or get_settings()
    model = llm or create_chat_model(settings)
    tools = demo_tools()
    bound = model.bind_tools(tools)

    def call_model(state: MessagesState) -> dict[str, list[Any]]:
        response = bound.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    # ToolNode executes AIMessage.tool_calls and appends ToolMessages.
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", route_after_model)
    graph.add_edge("tools", "call_model")

    return graph.compile(checkpointer=checkpointer)
