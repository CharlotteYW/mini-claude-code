"""Multi-agent handoff / swarm-lite (M35).

M12 ``run_subagent`` = hierarchical nested invoke (parent keeps control).
M35 = **control transfer**: ``active_agent`` changes; bounce cap stops ping-pong.

Sidecar graph only — default product ReAct is unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolCallId, StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import InjectedState, ToolNode
from langgraph.types import Command
from typing_extensions import TypedDict

AgentName = Literal["supervisor", "researcher", "writer"]

AGENT_NAMES: tuple[AgentName, ...] = ("supervisor", "researcher", "writer")

# Star topology: specialists hand back to supervisor only.
HANDOFF_ALLOW: dict[str, frozenset[str]] = {
    "supervisor": frozenset({"researcher", "writer"}),
    "researcher": frozenset({"supervisor"}),
    "writer": frozenset({"supervisor"}),
}

DEFAULT_MAX_HANDOFFS = 4

AGENT_BRIEFS: dict[str, str] = {
    "supervisor": (
        "You are the supervisor. Route work with handoff_to(researcher|writer). "
        "When the task is complete, call finish(summary). Be brief."
    ),
    "researcher": (
        "You are the researcher. Gather facts into the scratchpad via handoff note; "
        "then handoff_to(supervisor). You have no file tools — reason from the task text. "
        "Call finish only if supervisor told you to close."
    ),
    "writer": (
        "You are the writer. Produce a short final draft from the task + scratchpad; "
        "then handoff_to(supervisor) or finish if the draft is the answer."
    ),
}


class HandoffState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    active_agent: str
    handoff_count: int
    scratchpad: str
    user_task: str
    status: str  # running | done | capped
    turn_start_index: int


class HandoffError(ValueError):
    """Invalid handoff target or cap exceeded (fail closed)."""


def apply_handoff(
    *,
    active_agent: str,
    target: str,
    reason: str,
    handoff_count: int,
    scratchpad: str,
    note: str = "",
    max_handoffs: int = DEFAULT_MAX_HANDOFFS,
    message_len: int = 0,
) -> dict[str, Any]:
    """Pure handoff transition (unit-testable without a graph)."""
    target = target.strip()
    if target not in AGENT_NAMES:
        raise HandoffError(f"unknown agent {target!r}; choose from {AGENT_NAMES}")
    allowed = HANDOFF_ALLOW.get(active_agent, frozenset())
    if target not in allowed:
        raise HandoffError(
            f"{active_agent!r} cannot hand off to {target!r}; allowed={sorted(allowed)}"
        )
    if target == active_agent:
        raise HandoffError("cannot hand off to the already-active agent")
    next_count = handoff_count + 1
    if next_count > max_handoffs:
        raise HandoffError(
            f"handoff bounce cap exceeded ({max_handoffs}); refusing {active_agent}→{target}"
        )
    pad = scratchpad
    if note.strip():
        pad = (pad + "\n" if pad else "") + f"[{active_agent}→{target}] {note.strip()}"
    marker = SystemMessage(
        content=f"[handoff] {active_agent} → {target}: {reason.strip() or '(no reason)'}"
    )
    return {
        "active_agent": target,
        "handoff_count": next_count,
        "scratchpad": pad,
        "status": "running",
        "turn_start_index": message_len,  # marker becomes messages[message_len]
        "messages": [marker],
    }


def filter_messages_for_agent(state: HandoffState) -> list[BaseMessage]:
    """Build the prompt view for ``active_agent`` (isolation teaching point)."""
    agent = state["active_agent"]
    brief = AGENT_BRIEFS.get(agent, f"You are {agent}.")
    view: list[BaseMessage] = [
        SystemMessage(content=brief),
        HumanMessage(content=f"User task:\n{state['user_task']}"),
    ]
    pad = (state.get("scratchpad") or "").strip()
    if pad:
        view.append(SystemMessage(content=f"Shared scratchpad:\n{pad}"))

    messages = list(state.get("messages") or [])
    if agent == "supervisor":
        # Supervisor may see the transcript but not other agents' raw ToolMessages.
        for m in messages:
            if isinstance(m, AIMessage) and m.tool_calls:
                view.append(
                    AIMessage(
                        content=m.content
                        or f"(tool_calls: {[c.get('name') if isinstance(c, dict) else c for c in m.tool_calls]})"
                    )
                )
            elif type(m).__name__ == "ToolMessage":
                continue
            else:
                view.append(m)
        return view

    start = int(state.get("turn_start_index") or 0)
    view.extend(messages[start:])
    return view


def build_handoff_tools(*, max_handoffs: int = DEFAULT_MAX_HANDOFFS) -> list[BaseTool]:
    """Tools that transfer control via ``Command`` (not nested subagent invoke)."""

    def _handoff_to(
        agent: str,
        reason: str,
        note: str = "",
        state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command | str:
        assert state is not None
        try:
            msgs = list(state.get("messages") or [])
            update = apply_handoff(
                active_agent=str(state.get("active_agent") or "supervisor"),
                target=agent,
                reason=reason,
                handoff_count=int(state.get("handoff_count") or 0),
                scratchpad=str(state.get("scratchpad") or ""),
                note=note,
                max_handoffs=max_handoffs,
                message_len=len(msgs),
            )
        except HandoffError as exc:
            return f"ERROR: {exc}"
        marker = update.pop("messages")[0]
        # ToolNode requires a ToolMessage matching this tool_call_id inside Command.
        update["messages"] = [
            ToolMessage(
                content=f"handed off to {agent}: {reason}",
                tool_call_id=tool_call_id,
                name="handoff_to",
            ),
            marker,
        ]
        # turn_start_index: after ToolMessage+marker appended to prior len
        update["turn_start_index"] = len(msgs) + 1  # index of marker
        return Command(update=update, goto="agent")

    def _finish(
        summary: str,
        state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Command:
        text = summary.strip() or "(done)"
        return Command(
            update={
                "status": "done",
                "messages": [
                    ToolMessage(
                        content=f"finished: {text}",
                        tool_call_id=tool_call_id,
                        name="finish",
                    ),
                    AIMessage(content=f"[finish] {text}"),
                ],
            },
            goto=END,
        )

    return [
        StructuredTool.from_function(
            _handoff_to,
            name="handoff_to",
            description=(
                "Transfer control to another agent (supervisor|researcher|writer). "
                "Optional note is appended to the shared scratchpad."
            ),
        ),
        StructuredTool.from_function(
            _finish,
            name="finish",
            description="End the handoff demo with a final summary.",
        ),
    ]


def build_handoff_graph(
    llm: BaseChatModel,
    *,
    max_handoffs: int = DEFAULT_MAX_HANDOFFS,
):
    """Compile supervisor-star handoff graph (sidecar)."""
    tools = build_handoff_tools(max_handoffs=max_handoffs)
    tool_node = ToolNode(tools)
    bound = llm.bind_tools(tools)

    def agent_node(state: HandoffState, config: RunnableConfig) -> dict[str, Any]:
        if state.get("status") in {"done", "capped"}:
            return {}
        if int(state.get("handoff_count") or 0) > max_handoffs:
            return {
                "status": "capped",
                "messages": [
                    AIMessage(
                        content=f"[capped] handoff limit {max_handoffs} exceeded"
                    )
                ],
            }
        prompt = filter_messages_for_agent(state)
        response = bound.invoke(prompt, config)
        return {"messages": [response]}

    def route_after_agent(state: HandoffState) -> Literal["tools", "__end__"]:
        if state.get("status") in {"done", "capped"}:
            return END
        last = (state.get("messages") or [])[-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        # Plain text without finish — end to avoid free-chat loops in the demo.
        return END

    g = StateGraph(HandoffState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tool_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent)
    g.add_edge("tools", "agent")
    return g.compile()


def initial_handoff_state(task: str) -> HandoffState:
    return {
        "messages": [],
        "active_agent": "supervisor",
        "handoff_count": 0,
        "scratchpad": "",
        "user_task": task.strip(),
        "status": "running",
        "turn_start_index": 0,
    }


def contrast_blurb() -> str:
    return (
        "M12 run_subagent=parent keeps control (nested invoke). "
        "M35 handoff=active_agent transfers; bounce cap stops ping-pong; "
        "specialists see turn-local messages + scratchpad, not peer tool soup."
    )


def run_handoff_demo(
    llm: BaseChatModel,
    task: str,
    *,
    max_handoffs: int = DEFAULT_MAX_HANDOFFS,
    config: RunnableConfig | None = None,
) -> HandoffState:
    """Invoke the sidecar graph once and return final state values."""
    graph = build_handoff_graph(llm, max_handoffs=max_handoffs)
    out = graph.invoke(initial_handoff_state(task), config or {"recursion_limit": 20})
    return out  # type: ignore[return-value]


__all__ = [
    "AGENT_BRIEFS",
    "AGENT_NAMES",
    "DEFAULT_MAX_HANDOFFS",
    "HANDOFF_ALLOW",
    "HandoffError",
    "HandoffState",
    "apply_handoff",
    "build_handoff_graph",
    "build_handoff_tools",
    "contrast_blurb",
    "filter_messages_for_agent",
    "initial_handoff_state",
    "run_handoff_demo",
]
