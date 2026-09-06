"""M24 unit tests: shell hooks, allowlist, /pick."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.tools import StructuredTool

from mini_claude_code.agent.hooks import (
    HookRegistry,
    apply_hooks,
    load_hook_registry_from_dict,
    run_pre_hooks,
)
from mini_claude_code.agent.plugins import (
    load_plugin_manifest,
    plugin_examples_dir,
    resolve_plugins,
)
from mini_claude_code.agent.shell_hooks import (
    is_path_allowed,
    parse_post_stdout,
    parse_pre_stdout,
    resolve_script_argv,
)
from mini_claude_code.agent.slash_commands import (
    dispatch_slash_input,
    format_pick_list,
    resolve_pick_selection,
)
from mini_claude_code.config import Settings

pytestmark = pytest.mark.unit


def test_parse_hook_entry_script_vs_id() -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "shell-hooks" / "plugin.yaml")
    pre = pack.hooks["pre_tool_use"]
    assert any(isinstance(x, dict) and x.get("type") == "script" for x in pre)
    assert Path(pre[0]["path"]).name == "deny_forbidden_m24.py"


def test_reject_unknown_hook_type(tmp_path: Path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "plugin.yaml").write_text(
        "name: bad\nhooks:\n  pre_tool_use:\n    - type: http\n      url: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown type"):
        load_plugin_manifest(d / "plugin.yaml")


def test_parse_pre_stdout_deny_and_allow() -> None:
    denied = parse_pre_stdout(
        json.dumps({"allow": False, "reason": "nope"}), returncode=0
    )
    assert denied.allow is False
    assert denied.reason == "nope"
    allowed = parse_pre_stdout(json.dumps({"allow": True}), returncode=0)
    assert allowed.allow is True


def test_parse_post_stdout_rewrites() -> None:
    out = parse_post_stdout(json.dumps({"result": "new"}), prior="old")
    assert out == "new"
    assert parse_post_stdout("", prior="keep") == "keep"


def test_shell_pre_denies_via_script(tmp_path: Path) -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "shell-hooks" / "plugin.yaml")
    settings = Settings(
        _env_file=None,
        hook_shell_enabled=True,
        hook_shell_allowlist="",
        workspace_root=str(tmp_path),
    )
    # Script path is absolute under package examples — allow via allowlist
    script = Path(pack.hooks["pre_tool_use"][0]["path"])
    settings = Settings(
        _env_file=None,
        hook_shell_enabled=True,
        hook_shell_allowlist=str(script),
        workspace_root=str(tmp_path),
    )
    reg = load_hook_registry_from_dict(
        {"pre_tool_use": pack.hooks["pre_tool_use"]},
        settings=settings,
        workspace_root=tmp_path,
        base_dir=None,
    )
    assert len(reg.pre) == 1
    denied = run_pre_hooks(
        reg, tool="run_shell", args={"command": "echo FORBIDDEN_M24"}
    )
    assert denied.allow is False
    assert "FORBIDDEN_M24" in (denied.reason or "")
    allowed = run_pre_hooks(reg, tool="run_shell", args={"command": "echo ok"})
    assert allowed.allow is True


def test_shell_disabled_skips_entry(tmp_path: Path) -> None:
    pack = load_plugin_manifest(plugin_examples_dir() / "shell-hooks" / "plugin.yaml")
    script = Path(pack.hooks["pre_tool_use"][0]["path"])
    settings = Settings(
        _env_file=None,
        hook_shell_enabled=False,
        hook_shell_allowlist=str(script),
        workspace_root=str(tmp_path),
    )
    reg = load_hook_registry_from_dict(
        {"pre_tool_use": pack.hooks["pre_tool_use"]},
        settings=settings,
        workspace_root=tmp_path,
    )
    assert reg.pre == []


def test_allowlist_rejects_outside(tmp_path: Path) -> None:
    outsider = tmp_path / "evil.py"
    outsider.write_text("print('x')\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        hook_shell_enabled=True,
        hook_shell_allowlist=str(tmp_path / "other"),
        workspace_root=str(tmp_path / "ws"),
    )
    assert is_path_allowed(outsider, settings=settings, workspace_root=tmp_path / "ws") is False
    with pytest.raises(ValueError, match="not allowlisted"):
        load_hook_registry_from_dict(
            {
                "pre_tool_use": [
                    {"type": "script", "path": str(outsider.resolve())}
                ]
            },
            settings=settings,
            workspace_root=tmp_path / "ws",
        )


def test_m15_id_hooks_still_work() -> None:
    settings = Settings(_env_file=None, hook_shell_enabled=False)
    reg = load_hook_registry_from_dict(
        {"pre_tool_use": ["block_dangerous_shell"]},
        settings=settings,
    )
    assert len(reg.pre) == 1

    def run_shell(command: str) -> str:
        return "ran"

    wrapped = apply_hooks(
        [StructuredTool.from_function(run_shell, name="run_shell", description="s")],
        reg,
    )[0]
    assert "HOOK_DENIED" in str(wrapped.invoke({"command": "rm -rf /"}))


def test_pick_list_and_resolve() -> None:
    registry = {
        "review": {
            "description": "rev",
            "template": "Review {{args}}",
            "plugin_id": "review",
        },
        "docs": {
            "description": "docs",
            "template": "Docs {{args}}",
            "plugin_id": "docs-mcp",
        },
    }
    d = dispatch_slash_input("/pick", registry)
    assert d.kind == "pick"
    assert "1." in d.list_text
    text = format_pick_list(d.pick_choices)
    assert "/docs" in text
    # sorted: docs=1, review=2
    expanded = resolve_pick_selection(registry, "2", args="tests")
    assert "Review tests" in expanded


def test_empty_slash_is_pick() -> None:
    d = dispatch_slash_input("/", {})
    assert d.kind == "pick"


def test_resolve_script_argv_py_uses_interpreter() -> None:
    script = plugin_examples_dir() / "shell-hooks" / "hooks" / "deny_forbidden_m24.py"
    argv = resolve_script_argv(
        {"type": "script", "path": str(script)}, base_dir=None
    )
    assert argv[0].endswith("python") or "python" in Path(argv[0]).name
    assert argv[1] == str(script.resolve())


def test_seed_includes_shell_hooks(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    settings = Settings(_env_file=None, plugins_enabled=True, workspace_root=str(ws))
    packs = resolve_plugins(settings, workspace_root=ws, seed_examples=True)
    assert "shell-hooks" in {p.id for p in packs}
