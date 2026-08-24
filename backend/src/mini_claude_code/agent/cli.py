"""CLI entrypoint for the M2 ReAct agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.config import get_settings, resolve_workspace_root


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _format_message(message: object) -> str:
    if isinstance(message, HumanMessage):
        return f"Human: {message.content}"
    if isinstance(message, ToolMessage):
        return f"Tool[{message.name} id={message.tool_call_id}]: {message.content}"
    if isinstance(message, AIMessage):
        parts: list[str] = []
        if message.tool_calls:
            calls = ", ".join(
                f"{tc.get('name')}({tc.get('args')})" for tc in message.tool_calls
            )
            parts.append(f"AI tool_calls: {calls}")
        if message.content:
            parts.append(f"AI: {message.content}")
        return " | ".join(parts) if parts else "AI: (empty)"
    return f"{type(message).__name__}: {message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the mini-claude-code ReAct agent.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Use the add tool to compute 17 + 25. Do not compute it yourself.",
        help="User prompt (default forces add tool).",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Enable in-memory MemorySaver with this thread id (not durable — M5).",
    )
    parser.add_argument(
        "--new-thread",
        action="store_true",
        help="Like --thread-id with a random id (demo multi-turn checkpointer API).",
    )
    args = parser.parse_args(argv)

    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    thread_id = args.thread_id
    checkpointer = None
    if args.new_thread or thread_id:
        checkpointer = MemorySaver()
        thread_id = thread_id or str(uuid4())

    print("mini-claude-code agent (FS + shell/git tools)")
    print(f"  provider:  {settings.llm_provider}")
    print(f"  model:     {settings.llm_model}")
    print(f"  workspace: {resolve_workspace_root(settings)}")
    print("  note:      run_shell is host subprocess (not sandboxed until M11)")
    if thread_id:
        print(f"  thread:   {thread_id} (MemorySaver — process-local only)")
    print(f"  prompt:   {args.prompt}")
    print()

    try:
        graph = build_agent_graph(settings=settings, checkpointer=checkpointer)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    config: dict = {"recursion_limit": DEFAULT_RECURSION_LIMIT}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=args.prompt)]},
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: agent invoke failed: {exc}", file=sys.stderr)
        return 1

    print("=== transcript ===")
    for message in result["messages"]:
        print(_format_message(message))
    print("=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
