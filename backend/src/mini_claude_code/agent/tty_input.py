"""TTY line input that does not rely on terminal backspace column math.

Cursor/VS Code xterm often mis-handles CJK backspace (English works). We put
the terminal in cbreak, treat backspace ourselves, and **full-line redraw**
after each edit so display never depends on erase-char width.
"""

from __future__ import annotations

import sys
import termios
import tty
from collections.abc import Callable
from typing import TextIO


def _decode_utf8_char(pending: bytearray, byte: int) -> str | None:
    """Append one byte; return a decoded character when a sequence completes."""
    pending.append(byte)
    try:
        ch = pending.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Need more bytes for this multi-byte sequence.
        if exc.reason == "unexpected end of data":
            return None
        # Invalid sequence — drop and keep going.
        pending.clear()
        return None
    pending.clear()
    return ch


def _skip_csi(read_byte: Callable[[], int | None]) -> None:
    """Consume an ANSI CSI / SS3 sequence after ESC was already read."""
    first = read_byte()
    if first is None:
        return
    if first == 0x5B:  # '[' CSI
        while True:
            b = read_byte()
            if b is None or (0x40 <= b <= 0x7E):
                return
    if first == 0x4F:  # 'O' SS3 (arrows on some terminals)
        read_byte()
        return
    # Other ESC- sequences: ignore the following byte if any.


def edit_line_from_bytes(
    read_byte: Callable[[], int | None],
    *,
    write: Callable[[str], None],
    prompt: str = "",
) -> str:
    """Pure-ish line editor driven by a byte reader (unit-testable).

    ``write`` receives full redraw strings (clear line + prompt + buffer).
    """
    buf: list[str] = []
    pending = bytearray()

    def redraw() -> None:
        # Erase whole line then rewrite — never send backspace to the terminal.
        write("\r\033[2K" + prompt + "".join(buf))

    redraw()
    while True:
        b = read_byte()
        if b is None:
            if not buf:
                raise EOFError
            write("\n")
            return "".join(buf)

        # Enter
        if b in (0x0A, 0x0D):
            write("\n")
            return "".join(buf)

        # Ctrl-C
        if b == 0x03:
            write("\n")
            raise KeyboardInterrupt

        # Ctrl-D → EOF when buffer empty, else ignore
        if b == 0x04:
            if not buf:
                write("\n")
                raise EOFError
            continue

        # Backspace / Delete
        if b in (0x08, 0x7F):
            if buf:
                buf.pop()
                redraw()
            continue

        # ESC — skip arrow / function key sequences
        if b == 0x1B:
            _skip_csi(read_byte)
            continue

        # Printable / UTF-8 (including CJK)
        if b < 0x20:
            continue  # other controls
        ch = _decode_utf8_char(pending, b)
        if ch is None:
            continue
        buf.append(ch)
        redraw()


def read_tty_line(
    prompt: str = "",
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> str:
    """Read one line; on a real TTY use redraw editor, else plain readline."""
    inn = stdin or sys.stdin
    out = stdout or sys.stdout

    # Non-interactive (tests, pipes): simple path.
    if not inn.isatty() or not out.isatty():
        label = prompt
        if label and not label.endswith("\n"):
            # Keep prior UX for pipes: prompt then same-line read is fine.
            label = label.rstrip() + "\n"
        if label:
            out.write(label)
            out.flush()
        line = inn.readline()
        if line == "":
            raise EOFError
        return line.rstrip("\n\r")

    # Interactive: label on its own line, then cbreak edit on the next.
    label = prompt.rstrip()
    if label:
        out.write(label + "\n")
        out.flush()

    fd = inn.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)

        def read_byte() -> int | None:
            chunk = inn.buffer.read(1)
            if not chunk:
                return None
            return chunk[0]

        def write(s: str) -> None:
            out.write(s)
            out.flush()

        return edit_line_from_bytes(read_byte, write=write, prompt="")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
