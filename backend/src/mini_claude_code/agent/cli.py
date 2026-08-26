"""CLI entrypoint for the ReAct agent (M2+ … M10 HITL interrupt)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.checkpointer import (
    CheckpointBackend,
    open_checkpointer,
)
from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.agent.hitl import invoke_with_hitl
from mini_claude_code.agent.stream_render import consume_agent_stream
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


def _print_transcript(messages: list[object]) -> None:
    print("=== transcript ===")
    for message in messages:
        print(_format_message(message))
    print("=== done ===")


def _run_once(
    graph,
    prompt: str,
    config: dict,
    *,
    stream: bool,
    plan_mode: bool,
) -> int:
    # Plan Mode has no ask interrupts — token streaming is fine.
    # Otherwise HITL uses invoke + Command(resume) (M10 teaching path).
    if stream and plan_mode:
        try:
            consume_agent_stream(graph, prompt, config)
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: agent run failed: {exc}", file=sys.stderr)
            return 1

    if stream and not plan_mode:
        print(
            "Note: HITL ask uses invoke + interrupt (not token stream). "
            "Use --plan for stream-only read sessions.",
            file=sys.stderr,
        )

    result, code = invoke_with_hitl(graph, prompt, config)
    if code != 0:
        return code
    if result and "messages" in result:
        _print_transcript(result["messages"])
    else:
        print("=== done ===")
    return 0


def _run_repl(
    graph, config: dict, *, stream: bool, plan_mode: bool
) -> int:
    print("REPL mode — empty line or Ctrl-D to exit.")
    while True:
        try:
            line = input("you> ").strip()
        except EOFError:
            print()
            break
        if not line:
            break
        code = _run_once(
            graph, line, config, stream=stream, plan_mode=plan_mode
        )
        if code != 0:
            return code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the mini-claude-code ReAct agent."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="User prompt (optional if --repl).",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Session id for checkpointer resume (required for durable/multi-turn/HITL).",
    )
    parser.add_argument(
        "--new-thread",
        action="store_true",
        help="Allocate a random thread id (prints it).",
    )
    parser.add_argument(
        "--checkpointer",
        choices=["memory", "postgres"],
        default=None,
        help="Override CHECKPOINT_BACKEND (default from env: postgres).",
    )
    parser.add_argument(
        "--repl",
        action="store_true",
        help="Interactive multi-turn loop (requires a thread id).",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Use invoke + full transcript instead of live streaming (Plan Mode).",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Plan Mode: deny mutating tools (read-only policy). Also AGENT_PLAN_MODE=1.",
    )
    args = parser.parse_args(argv)

    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    plan_mode = bool(args.plan or settings.agent_plan_mode)

    thread_id = args.thread_id
    if args.new_thread:
        thread_id = str(uuid4())
    if args.repl and not thread_id:
        thread_id = str(uuid4())
        print(f"Allocated thread_id={thread_id} for REPL")

    # Ask/HITL needs a checkpointer. Auto-allocate a thread when not in Plan Mode.
    if not plan_mode and not thread_id:
        thread_id = str(uuid4())
        print(
            f"HITL ask requires a session; allocated thread_id={thread_id}",
            file=sys.stderr,
        )

    use_checkpoint = bool(thread_id)
    if args.repl and not use_checkpoint:
        print("ERROR: --repl requires a thread id", file=sys.stderr)
        return 1
    if not args.repl and not args.prompt:
        args.prompt = (
            "Use write_file to create demo.txt with contents hello, then read_file it."
        )

    backend: CheckpointBackend | None = (
        args.checkpointer  # type: ignore[assignment]
        if args.checkpointer
        else None
    )
    stream = not args.no_stream

    print("mini-claude-code agent (FS + shell/git + sessions + stream + HITL)")
    print(f"  provider:     {settings.llm_provider}")
    print(f"  model:        {settings.llm_model}")
    print(f"  workspace:    {resolve_workspace_root(settings)}")
    print(f"  streaming:    {'on' if stream else 'off (--no-stream)'}")
    print(
        f"  plan_mode:    {'on (mutating tools denied)' if plan_mode else 'off'}"
    )
    print(
        "  hitl:         "
        + (
            "off (plan mode)"
            if plan_mode
            else "interrupt + Command(resume) on ask tools"
        )
    )
    if use_checkpoint:
        kind = backend or settings.checkpoint_backend
        print(f"  thread_id:    {thread_id}")
        print(f"  checkpointer: {kind}")
    else:
        print("  session:      off")
    if not args.repl:
        print(f"  prompt:       {args.prompt}")
    print()

    config: dict = {"recursion_limit": DEFAULT_RECURSION_LIMIT}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    def _build(checkpointer=None):
        return build_agent_graph(
            settings=settings,
            checkpointer=checkpointer,
            plan_mode=plan_mode,
            # Production path: interrupt inside wrap (no stdin ask_callback).
            ask_callback=None,
        )

    try:
        if use_checkpoint:
            with open_checkpointer(
                settings, backend=backend, setup=True
            ) as checkpointer:
                graph = _build(checkpointer)
                if args.repl:
                    return _run_repl(
                        graph, config, stream=stream, plan_mode=plan_mode
                    )
                return _run_once(
                    graph,
                    args.prompt or "",
                    config,
                    stream=stream,
                    plan_mode=plan_mode,
                )
        graph = _build(None)
        if args.repl:
            return _run_repl(
                graph, config, stream=stream, plan_mode=plan_mode
            )
        return _run_once(
            graph,
            args.prompt or "",
            config,
            stream=stream,
            plan_mode=plan_mode,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
