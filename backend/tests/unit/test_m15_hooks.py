"""M15 unit tests: hook registry, Pre deny, Post transform, exception policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import StructuredTool

from mini_claude_code.agent.hook_demos import (
    append_audit_marker,
    block_dangerous_shell,
    redact_secret_pattern,
)
from mini_claude_code.agent.hooks import (
    HookContext,
    HookRegistry,
    PreResult,
    apply_hooks,
    hook_denied_message,
    load_hook_registry_from_dict,
    load_hook_registry_from_yaml,
    resolve_hook_registry,
    run_post_hooks,
    run_pre_hooks,
)
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


def test_empty_registry_is_noop() -> None:
    called: list[str] = []

    def echo(text: str) -> str:
        called.append(text)
        return text

    raw = StructuredTool.from_function(echo, name="echo", description="echo")
    wrapped = apply_hooks([raw], HookRegistry())[0]
    assert wrapped is raw or wrapped.invoke({"text": "hi"}) == "hi"
    # empty registry returns same list identity of tools
    out = apply_hooks([raw], HookRegistry())
    assert out[0] is raw


def test_pre_deny_short_circuits_body() -> None:
    called: list[str] = []

    def run_shell(command: str) -> str:
        called.append(command)
        return "ran"

    raw = StructuredTool.from_function(
        run_shell, name="run_shell", description="shell"
    )
    registry = HookRegistry(pre=[block_dangerous_shell])
    wrapped = apply_hooks([raw], registry)[0]
    out = wrapped.invoke({"command": "rm -rf /"})
    assert "HOOK_DENIED" in str(out)
    assert called == []


def test_pre_allow_runs_body() -> None:
    def run_shell(command: str) -> str:
        return f"ok:{command}"

    raw = StructuredTool.from_function(
        run_shell, name="run_shell", description="shell"
    )
    registry = HookRegistry(pre=[block_dangerous_shell])
    wrapped = apply_hooks([raw], registry)[0]
    assert wrapped.invoke({"command": "echo hi"}) == "ok:echo hi"


def test_post_transforms_result() -> None:
    def echo(text: str) -> str:
        return text

    raw = StructuredTool.from_function(echo, name="echo", description="echo")
    registry = HookRegistry(post=[append_audit_marker])
    wrapped = apply_hooks([raw], registry)[0]
    out = wrapped.invoke({"text": "hello"})
    assert out == "hello\n[hook:audited]"


def test_post_redact_secret() -> None:
    ctx = HookContext(
        event="post_tool_use",
        tool="read_file",
        result="token SECRET=abc123 done",
    )
    assert redact_secret_pattern(ctx) == "token SECRET=*** done"


def test_pre_handler_exception_denies() -> None:
    def boom(_ctx: HookContext) -> None:
        raise RuntimeError("explode")

    pre = run_pre_hooks(HookRegistry(pre=[boom]), tool="echo", args={})
    assert pre.allow is False
    assert "error" in (pre.reason or "").lower()


def test_post_handler_exception_keeps_result() -> None:
    def boom(_ctx: HookContext) -> str:
        raise RuntimeError("explode")

    out = run_post_hooks(
        HookRegistry(post=[boom]),
        tool="echo",
        args={},
        result="original",
    )
    assert out == "original"


def test_load_yaml_and_resolve_demo(tmp_path: Path) -> None:
    path = tmp_path / "hooks.yaml"
    path.write_text(
        "pre_tool_use:\n  - block_dangerous_shell\n"
        "post_tool_use:\n  - append_audit_marker\n",
        encoding="utf-8",
    )
    reg = load_hook_registry_from_yaml(path)
    assert len(reg.pre) == 1
    assert len(reg.post) == 1

    settings = Settings(
        _env_file=None,
        hooks_use_demo=True,
        hooks_config_path="",
        workspace_root=str(tmp_path),
    )
    # no hooks.yaml in empty workspace dir → demo
    empty = tmp_path / "ws"
    empty.mkdir()
    settings2 = Settings(
        _env_file=None,
        hooks_use_demo=True,
        workspace_root=str(empty),
    )
    demo = resolve_hook_registry(settings2, workspace_root=empty)
    assert not demo.empty


def test_load_from_dict_unknown_id() -> None:
    with pytest.raises(ValueError, match="Unknown hook"):
        load_hook_registry_from_dict({"pre_tool_use": ["nope"]})


def test_hook_denied_message_format() -> None:
    msg = hook_denied_message("run_shell", "bad")
    assert msg.startswith("HOOK_DENIED:")
    assert "run_shell" in msg


def test_pre_can_rewrite_args() -> None:
    def rewrite(ctx: HookContext) -> PreResult:
        return PreResult(allow=True, args={"text": "rewritten"})

    seen: list[str] = []

    def echo(text: str) -> str:
        seen.append(text)
        return text

    raw = StructuredTool.from_function(echo, name="echo", description="echo")
    wrapped = apply_hooks([raw], HookRegistry(pre=[rewrite]))[0]
    assert wrapped.invoke({"text": "orig"}) == "rewritten"
    assert seen == ["rewritten"]
