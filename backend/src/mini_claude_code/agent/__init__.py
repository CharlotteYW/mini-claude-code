"""Agent package — LangGraph ReAct core (M2+) with checkpointers (M5)."""

from mini_claude_code.agent.checkpointer import (
    ensure_postgres_checkpoint_tables,
    open_checkpointer,
    resolve_checkpoint_backend,
)
from mini_claude_code.agent.graph import (
    DEFAULT_RECURSION_LIMIT,
    build_agent_graph,
    route_after_model,
)

__all__ = [
    "DEFAULT_RECURSION_LIMIT",
    "build_agent_graph",
    "ensure_postgres_checkpoint_tables",
    "open_checkpointer",
    "resolve_checkpoint_backend",
    "route_after_model",
]
