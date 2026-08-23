"""Agent package — LangGraph ReAct core (M2+)."""

from mini_claude_code.agent.graph import (
    DEFAULT_RECURSION_LIMIT,
    build_agent_graph,
    route_after_model,
)

__all__ = ["DEFAULT_RECURSION_LIMIT", "build_agent_graph", "route_after_model"]
