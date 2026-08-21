"""Shared demo tools for provider parity probes (M1).

Keep tools tiny and deterministic so failures are about *calling convention*,
not about ambiguous task wording.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


def demo_tools() -> list[BaseTool]:
    return [add]
