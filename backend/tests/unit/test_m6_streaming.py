"""M6 unit tests: token streaming + updates with a real BaseChatModel fake."""

from __future__ import annotations

from io import StringIO
from typing import Any, Iterator, List, Optional

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.stream_render import consume_agent_stream
from mini_claude_code.tools import demo_tools

pytestmark = pytest.mark.unit


class _StreamChat(BaseChatModel):
    """Minimal chat model that streams tokens through LangChain callbacks."""

    reply: str = "hello world"
    tool_call_once: bool = False
    _saw_tool_result: bool = False

    @property
    def _llm_type(self) -> str:
        return "m6-stream-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_StreamChat":
        return self

    def _next_message(self, messages: list[BaseMessage]) -> AIMessage:
        if self.tool_call_once and any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="sum=42")
        if self.tool_call_once and not any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "add",
                        "args": {"a": 17, "b": 25},
                        "id": "m6-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content=self.reply)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg = self._next_message(messages)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        msg = self._next_message(messages)
        if msg.tool_calls:
            chunk = ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_calls=msg.tool_calls)
            )
            yield chunk
            return
        for ch in str(msg.content):
            if run_manager:
                run_manager.on_llm_new_token(ch)
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))


def test_messages_stream_emits_multiple_token_chunks() -> None:
    graph = build_agent_graph(llm=_StreamChat(reply="hello"), tools=[])
    chunks = list(
        graph.stream(
            {"messages": [HumanMessage(content="hi")]},
            config={"recursion_limit": 10},
            stream_mode="messages",
        )
    )
    contents = [c[0].content for c in chunks if getattr(c[0], "content", None)]
    assert contents[:5] == ["h", "e", "l", "l", "o"]
    assert "".join(str(x) for x in contents if x) == "hello"


def test_updates_surface_tools_node() -> None:
    graph = build_agent_graph(
        llm=_StreamChat(tool_call_once=True), tools=demo_tools()
    )
    updates = [
        item
        for item in graph.stream(
            {"messages": [HumanMessage(content="add")]},
            config={"recursion_limit": 10},
            stream_mode="updates",
        )
        if isinstance(item, dict)
    ]
    assert any("tools" in u for u in updates)
    assert any("call_model" in u for u in updates)


def test_consume_agent_stream_prints_tokens_and_returns_messages() -> None:
    graph = build_agent_graph(llm=_StreamChat(reply="hello world"), tools=[])
    buf = StringIO()
    messages = consume_agent_stream(
        graph,
        "hi",
        {"recursion_limit": 10},
        out=buf,
    )
    text = buf.getvalue()
    assert "hello world" in text.replace("\n", "")
    assert "=== done ===" in text
    assert any(
        isinstance(m, AIMessage) and "hello world" in str(m.content) for m in messages
    )


def test_invoke_path_still_works() -> None:
    graph = build_agent_graph(llm=_StreamChat(reply="hello world"), tools=[])
    result = graph.invoke(
        {"messages": [HumanMessage(content="hi")]},
        config={"recursion_limit": 10},
    )
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.content == "hello world"


def test_stream_with_memory_checkpointer_accumulates() -> None:
    cp = MemorySaver()
    graph = build_agent_graph(
        llm=_StreamChat(reply="ok"), tools=[], checkpointer=cp
    )
    config = {
        "configurable": {"thread_id": "m6-unit"},
        "recursion_limit": 10,
    }
    consume_agent_stream(graph, "first", config, out=StringIO())
    consume_agent_stream(graph, "second", config, out=StringIO())
    snap = graph.get_state(config)
    humans = [m for m in snap.values["messages"] if isinstance(m, HumanMessage)]
    assert len(humans) >= 2
