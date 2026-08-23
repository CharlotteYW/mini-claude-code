"""M3 unit tests: path jail and filesystem tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_claude_code.tools.fs import build_coding_tools
from mini_claude_code.tools.path_jail import PathEscapeError, resolve_in_workspace

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "notes").mkdir()
    (root / "notes" / "a.txt").write_text("hello alpha\n", encoding="utf-8")
    (root / "notes" / "b.txt").write_text("hello beta\nfoo\n", encoding="utf-8")
    (root / "readme.md").write_text("# title\n", encoding="utf-8")
    return root


def test_path_jail_joins_relative(workspace: Path) -> None:
    resolved = resolve_in_workspace(workspace, "notes/a.txt")
    assert resolved == (workspace / "notes" / "a.txt").resolve()


def test_path_jail_rejects_escape(workspace: Path) -> None:
    with pytest.raises(PathEscapeError):
        resolve_in_workspace(workspace, "../outside.txt")


def test_read_write_round_trip(workspace: Path) -> None:
    tools = {t.name: t for t in build_coding_tools(workspace)}
    assert "OK" in tools["write_file"].invoke(
        {"path": "out/hello.txt", "content": "hi there"}
    )
    assert tools["read_file"].invoke({"path": "out/hello.txt"}) == "hi there"


def test_edit_file_unique_and_ambiguous(workspace: Path) -> None:
    tools = {t.name: t for t in build_coding_tools(workspace)}
    assert "OK" in tools["edit_file"].invoke(
        {"path": "notes/a.txt", "old_str": "alpha", "new_str": "ALPHA"}
    )
    assert "ALPHA" in tools["read_file"].invoke({"path": "notes/a.txt"})

    # two "hello" lines across intent — make ambiguous inside one file
    (workspace / "notes" / "dup.txt").write_text("x\nx\n", encoding="utf-8")
    err = tools["edit_file"].invoke(
        {"path": "notes/dup.txt", "old_str": "x", "new_str": "y"}
    )
    assert err.startswith("ERROR:")
    assert "2 times" in err or "unique" in err

    missing = tools["edit_file"].invoke(
        {"path": "notes/a.txt", "old_str": "nope", "new_str": "y"}
    )
    assert "not found" in missing


def test_glob_and_grep(workspace: Path) -> None:
    tools = {t.name: t for t in build_coding_tools(workspace)}
    listed = tools["glob_files"].invoke({"pattern": "notes/*.txt"})
    assert "notes/a.txt" in listed
    assert "notes/b.txt" in listed

    grepped = tools["grep_files"].invoke(
        {"pattern": "beta", "glob_pattern": "**/*.txt"}
    )
    assert "notes/b.txt" in grepped
    assert "beta" in grepped


def test_write_escape_returns_error(workspace: Path) -> None:
    tools = {t.name: t for t in build_coding_tools(workspace)}
    err = tools["write_file"].invoke(
        {"path": "../pwned.txt", "content": "nope"}
    )
    assert err.startswith("ERROR:")
    assert not (workspace.parent / "pwned.txt").exists()
