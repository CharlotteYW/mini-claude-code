"""Shared demo tools (M1 parity + M2 ReAct stubs).

Keep tools tiny and deterministic so failures are about *calling convention*
or graph routing — not ambiguous task wording.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


@tool
def get_agent_name() -> str:
    """Return this learning agent's short name."""
    return "mini-claude-code"


def demo_tools() -> list[BaseTool]:
    return [add, get_agent_name]
