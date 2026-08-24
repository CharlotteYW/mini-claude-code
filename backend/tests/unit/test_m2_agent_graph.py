"""M2 unit tests: routing, ToolNode behavior, compile, fake-LLM full invoke."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from langgraph.prebuilt import ToolNode

from mini_claude_code.agent.graph import build_agent_graph, route_after_model
from mini_claude_code.tools import add, demo_tools

pytestmark = pytest.mark.unit


def test_route_after_model_to_tools() -> None:
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 1, "b": 2},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    }
    assert route_after_model(state) == "tools"  # type: ignore[arg-type]


def test_route_after_model_to_end() -> None:
    state = {"messages": [AIMessage(content="done — no tools")]}
    assert route_after_model(state) == END  # type: ignore[arg-type]


def test_tools_node_executes_add() -> None:
    from langgraph.graph import START, StateGraph
    from langgraph.graph import MessagesState

    # ToolNode expects graph runtime context in recent LangGraph; invoke via a tiny graph.
    g = StateGraph(MessagesState)
    g.add_node("tools", ToolNode(demo_tools()))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    compiled = g.compile()

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "add",
                "args": {"a": 17, "b": 25},
                "id": "call-add-1",
                "type": "tool_call",
            }
        ],
    )
    out = compiled.invoke({"messages": [ai]})
    messages = out["messages"]
    tm = messages[-1]
    assert isinstance(tm, ToolMessage)
    assert tm.tool_call_id == "call-add-1"
    assert tm.content == "42"
    assert tm.name == add.name


def test_build_agent_graph_node_names() -> None:
    graph = build_agent_graph(llm=_FakeLLM(), tools=demo_tools())
    # Compiled graphs expose node names via get_graph / nodes depending on version.
    names = set(graph.get_graph().nodes)
    assert "call_model" in names
    assert "tools" in names


class _FakeBound:
    def invoke(self, messages: list[Any], config: Any = None) -> AIMessage:
        has_tool_result = any(isinstance(m, ToolMessage) for m in messages)
        if has_tool_result:
            return AIMessage(content="The sum of 17 and 25 is 42.")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "add",
                    "args": {"a": 17, "b": 25},
                    "id": "fake-1",
                    "type": "tool_call",
                }
            ],
        )


class _FakeLLM:
    def bind_tools(self, _tools: Any) -> _FakeBound:
        return _FakeBound()


def test_full_graph_invoke_with_fake_llm() -> None:
    graph = build_agent_graph(llm=_FakeLLM(), tools=demo_tools())
    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content="Use the add tool to compute 17 + 25."
                )
            ]
        },
        config={"recursion_limit": 10},
    )
    messages = result["messages"]
    assert any(isinstance(m, ToolMessage) and m.content == "42" for m in messages)
    last = messages[-1]
    assert isinstance(last, AIMessage)
    assert "42" in str(last.content)
