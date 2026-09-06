"""CJK-safe TTY line editor (redraw on backspace)."""

from __future__ import annotations

import io

import pytest

from mini_claude_code.agent.tty_input import edit_line_from_bytes, read_tty_line

pytestmark = pytest.mark.unit


def _bytes_reader(data: bytes):
    view = memoryview(data)
    i = 0

    def read_byte() -> int | None:
        nonlocal i
        if i >= len(view):
            return None
        b = view[i]
        i += 1
        return b

    return read_byte


def test_edit_line_cjk_backspace_removes_all_chars() -> None:
    # 你 好 啊 then three backspaces then Enter — buffer must be empty.
    payload = "你好啊".encode() + bytes([0x7F, 0x7F, 0x7F, 0x0A])
    out: list[str] = []
    result = edit_line_from_bytes(
        _bytes_reader(payload), write=out.append, prompt=""
    )
    assert result == ""
    # Final redraw before enter should be clear-line only (empty buf).
    assert any(s.endswith("\033[2K") or s == "\r\033[2K" for s in out)


def test_edit_line_keeps_remaining_cjk_after_partial_delete() -> None:
    # Type three CJK, delete two → first char remains.
    payload = "你好啊".encode() + bytes([0x7F, 0x7F, 0x0A])
    result = edit_line_from_bytes(
        _bytes_reader(payload), write=lambda _s: None, prompt=""
    )
    assert result == "你"


def test_edit_line_english_and_cjk() -> None:
    payload = b"hi" + "中".encode() + bytes([0x0A])
    result = edit_line_from_bytes(
        _bytes_reader(payload), write=lambda _s: None, prompt=""
    )
    assert result == "hi中"


def test_read_tty_line_non_tty_strips_newline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("你好啊\n"))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert read_tty_line("you> ") == "你好啊"
    assert out.getvalue() == "you>\n"


def test_read_tty_line_eof_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(EOFError):
        read_tty_line()
