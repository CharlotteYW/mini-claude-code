"""M26 integration: fake_docs MCP server-side + client wrap (skip if MCP unavailable)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import build_agent_graph
from mini_claude_code.agent.permissions import apply_permissions
from mini_claude_code.config import Settings
from mini_claude_code.content_policy import apply_content_policy_wrap
from mini_claude_code.tools.mcp_loader import fake_docs_connections, load_mcp_tools_sync

pytestmark = pytest.mark.integration

_SECRET_MARKERS = ("SECRET_BODY_M26_ALPHA", "SECRET_BODY_M26_BETA")


def _fake_docs_or_skip() -> dict[str, Any]:
    try:
        tools = load_mcp_tools_sync(fake_docs_connections())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"fake_docs MCP unavailable: {exc}")
    by_name = {t.name: t for t in tools}
    if "read_doc" not in by_name or "list_docs" not in by_name:
        pytest.skip(f"unexpected fake_docs tools: {sorted(by_name)}")
    return by_name


def test_server_denies_no_ai_doc() -> None:
    tools = _fake_docs_or_skip()
    out = tools["read_doc"].invoke({"doc_id": "secret-no-ai"})
    assert "CONTENT_POLICY_DENIED" in str(out)
    for secret in _SECRET_MARKERS:
        assert secret not in str(out)


def test_server_denies_confidential_doc() -> None:
    tools = _fake_docs_or_skip()
    out = tools["read_doc"].invoke({"doc_id": "confidential-memo"})
    assert "CONTENT_POLICY_DENIED" in str(out)
    assert "SECRET_BODY_M26_BETA" not in str(out)


def test_server_allows_clean_doc() -> None:
    tools = _fake_docs_or_skip()
    out = str(tools["read_doc"].invoke({"doc_id": "clean-guide"}))
    assert "CONTENT_POLICY_DENIED" not in out
    assert "safe for AI" in out.lower() or "uv" in out.lower()


def test_list_docs_does_not_leak_bodies() -> None:
    tools = _fake_docs_or_skip()
    listing = str(tools["list_docs"].invoke({}))
    for secret in _SECRET_MARKERS:
        assert secret not in listing
    assert "secret-no-ai" in listing
    assert "clean-guide" in listing


class _FakeReadDocCaller(BaseChatModel):
    """Call read_doc on secret-no-ai, then finish."""

    def __init__(self) -> None:
        super().__init__()
        self._n = 0

    @property
    def _llm_type(self) -> str:
        return "fake-m26"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self._n += 1
        if self._n == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_doc",
                        "args": {"doc_id": "secret-no-ai"},
                        "id": "m26-1",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="denied as expected")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self


def test_graph_ainvoke_read_doc_denied(tmp_path) -> None:
    raw = list(_fake_docs_or_skip().values())
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        llm_model="x",
        workspace_root=str(tmp_path),
        context_compact_threshold=0,
        content_policy_enabled=True,
        mcp_use_fake_docs=False,
    )
    screened = apply_content_policy_wrap(raw, settings=settings)
    wrapped = apply_permissions(screened, plan_mode=False, ask_callback=lambda *_: True)
    graph = build_agent_graph(
        settings=settings,
        llm=_FakeReadDocCaller(),
        tools=wrapped,
        checkpointer=MemorySaver(),
        apply_tool_permissions=False,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="read secret-no-ai")]},
        config={"configurable": {"thread_id": "m26-int"}},
    )
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs
    content = str(tool_msgs[0].content)
    assert "CONTENT_POLICY_DENIED" in content
    assert "SECRET_BODY_M26_ALPHA" not in content
    blob = "\n".join(str(getattr(m, "content", "")) for m in result["messages"])
    assert "SECRET_BODY_M26_ALPHA" not in blob
