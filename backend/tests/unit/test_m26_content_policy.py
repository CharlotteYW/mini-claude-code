"""M26 unit tests: marker detection, client wrap, builtin read_file path."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.tools import tool

from mini_claude_code.agent.permissions import resolve_permission
from mini_claude_code.config import Settings
from mini_claude_code.content_policy import (
    apply_content_policy_wrap,
    filter_tool_result,
    find_policy_marker,
)
from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.mcp_loader import (
    fake_docs_connections,
    resolve_mcp_connections,
)

pytestmark = pytest.mark.unit


def test_find_marker_first_line_no_ai() -> None:
    text = "no-ai — withhold\n\nSECRET_BODY_SHOULD_NOT_LEAK\n"
    assert find_policy_marker(text) == "no-ai"


def test_find_marker_h1_confidential_case_insensitive() -> None:
    text = "# CONFIDENTIAL — memo\n\nSECRET_BODY\n"
    assert find_policy_marker(text, markers=["CONFIDENTIAL"]) == "CONFIDENTIAL"


def test_find_marker_title_arg() -> None:
    assert (
        find_policy_marker("benign body only", title="Project no-ai notes") == "no-ai"
    )


def test_clean_doc_no_marker() -> None:
    text = "# Clean onboarding guide\n\nSafe for AI.\n"
    assert find_policy_marker(text) is None


def test_filter_replaces_body() -> None:
    raw = "no-ai\nSECRET_BODY_M26_ALPHA\n"
    out = filter_tool_result(raw)
    assert isinstance(out, str)
    assert out.startswith("CONTENT_POLICY_DENIED:")
    assert "SECRET_BODY_M26_ALPHA" not in out


def test_client_wrap_denies_leaky_mock() -> None:
    @tool
    def read_doc(doc_id: str) -> str:
        """Mock MCP read that returns a marked body (hostile/forgetful server)."""
        return "no-ai\nSECRET_BODY_M26_ALPHA leak\n"

    settings = Settings(_env_file=None, content_policy_enabled=True)
    wrapped = apply_content_policy_wrap([read_doc], settings=settings)
    assert len(wrapped) == 1
    result = wrapped[0].invoke({"doc_id": "x"})
    assert "CONTENT_POLICY_DENIED" in result
    assert "SECRET_BODY_M26_ALPHA" not in result


def test_client_wrap_passes_clean() -> None:
    @tool
    def read_doc(doc_id: str) -> str:
        """Clean body."""
        return "# Clean guide\n\nHello from clean fixture.\n"

    settings = Settings(_env_file=None, content_policy_enabled=True)
    wrapped = apply_content_policy_wrap([read_doc], settings=settings)
    result = wrapped[0].invoke({"doc_id": "clean"})
    assert "Hello from clean fixture" in result
    assert "CONTENT_POLICY_DENIED" not in result


def test_wrap_disabled_passes_secret() -> None:
    @tool
    def read_doc(doc_id: str) -> str:
        """Leaks when policy off."""
        return "no-ai\nSECRET_BODY_M26_ALPHA\n"

    settings = Settings(_env_file=None, content_policy_enabled=False)
    wrapped = apply_content_policy_wrap([read_doc], settings=settings)
    assert wrapped[0].invoke({"doc_id": "x"}) == "no-ai\nSECRET_BODY_M26_ALPHA\n"


def test_builtin_read_file_respects_markers(tmp_path: Path) -> None:
    secret = tmp_path / "secret.md"
    secret.write_text("no-ai\nSECRET_BODY_M26_FILE\n", encoding="utf-8")
    tools = {t.name: t for t in build_coding_tools(tmp_path)}
    settings = Settings(
        _env_file=None,
        content_policy_enabled=True,
        content_policy_wrap_builtin_read=True,
    )
    wrapped = {t.name: t for t in apply_content_policy_wrap([tools["read_file"]], settings=settings)}
    out = wrapped["read_file"].invoke({"path": "secret.md"})
    assert "CONTENT_POLICY_DENIED" in out
    assert "SECRET_BODY_M26_FILE" not in out


def test_permissions_still_auto_for_read_doc() -> None:
    assert resolve_permission("read_doc", plan_mode=False) == "auto"
    assert resolve_permission("list_docs", plan_mode=False) == "auto"


def test_resolve_fake_docs_flag() -> None:
    settings = Settings(
        _env_file=None,
        mcp_config="",
        mcp_config_path="",
        mcp_use_demo=False,
        mcp_use_fake_docs=True,
    )
    conns = resolve_mcp_connections(settings)
    assert "fake_docs" in conns
    assert Path(conns["fake_docs"]["args"][0]).name == "fake_docs.py"
    assert fake_docs_connections()["fake_docs"]["transport"] == "stdio"


def test_resolve_demo_and_fake_docs_merge() -> None:
    settings = Settings(
        _env_file=None,
        mcp_use_demo=True,
        mcp_use_fake_docs=True,
        mcp_config="",
        mcp_config_path="",
    )
    conns = resolve_mcp_connections(settings)
    assert set(conns) == {"echo_math", "fake_docs"}
