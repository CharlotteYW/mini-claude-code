"""CLI entrypoint for the ReAct agent (M2+ … M10 HITL; M22 async-first)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.agent.checkpointer import (
    CheckpointBackend,
    open_async_checkpointer,
    open_checkpointer,
)
from mini_claude_code.agent.graph import DEFAULT_RECURSION_LIMIT, build_agent_graph
from mini_claude_code.agent.hitl import (
    ainvoke_with_hitl,
    format_run_error,
    invoke_with_hitl,
)
from mini_claude_code.agent.plugins import PluginPack, resolve_plugins
from mini_claude_code.agent.slash_commands import (
    dispatch_slash_input,
    resolve_pick_selection,
    slash_registry_from_plugins,
)
from mini_claude_code.agent.store import (
    open_async_store,
    open_store,
    resolve_store_backend,
    store_namespace,
)
from mini_claude_code.agent.stream_render import (
    consume_agent_astream,
    consume_agent_stream,
)
from mini_claude_code.agent.time_travel import (
    afork_from_checkpoint,
    alist_checkpoints,
    fork_from_checkpoint,
    format_checkpoint_table,
    list_checkpoints,
    parse_rewind_args,
    resolve_checkpoint_ref,
)
from mini_claude_code.agent.structured import (
    RouteDecision,
    contrast_blurb,
    first_tool_call_name,
    invoke_forced_tool,
    invoke_structured,
)
from mini_claude_code.agent.handoff import (
    contrast_blurb as handoff_contrast_blurb,
    run_handoff_demo,
)
from mini_claude_code.agent.tracing import (
    JsonlTraceHandler,
    attach_callbacks,
    enrich_run_config,
    tracing_status,
)
from mini_claude_code.agent.tty_input import read_tty_line
from mini_claude_code.agent.usage import USAGE_ACCUMULATOR_KEY, UsageAccumulator
from mini_claude_code.config import get_settings, resolve_workspace_root
from mini_claude_code.llm import create_chat_model
from mini_claude_code.tools import demo_tools


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # agent/cli.py → …/mini_claude_code/agent → parents[4] = repo root
    repo_root = Path(__file__).resolve().parents[4]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _aresolve_fork_checkpoint_id_sync_list(
    graph,
    thread_id: str,
    ref: str,
    *,
    completed_only: bool,
) -> str:
    raw = ref.strip()
    if raw.isdigit():
        rows = list_checkpoints(graph, thread_id, completed_only=completed_only)
        return resolve_checkpoint_ref(rows, raw).checkpoint_id
    return raw


async def _aresolve_fork_checkpoint_id(
    graph,
    thread_id: str,
    ref: str,
    *,
    completed_only: bool,
) -> str:
    raw = ref.strip()
    if raw.isdigit():
        rows = await alist_checkpoints(
            graph, thread_id, completed_only=completed_only
        )
        return resolve_checkpoint_ref(rows, raw).checkpoint_id
    return raw


def _apply_fork_config(config: dict, fork_cfg: dict) -> None:
    """Switch session to the forked thread tip (do not pin a stale checkpoint_id)."""
    cfg = config.setdefault("configurable", {})
    fcfg = fork_cfg.get("configurable") or {}
    cfg["thread_id"] = fcfg["thread_id"]
    # update_state already wrote the tip for this thread; pinning the fork
    # checkpoint_id would make later get_state/invoke look at a frozen snapshot.
    cfg.pop("checkpoint_id", None)
    if "checkpoint_ns" in fcfg:
        cfg["checkpoint_ns"] = fcfg["checkpoint_ns"]


def _handle_rewind_sync(
    graph,
    config: dict,
    line: str,
    *,
    completed_only: bool,
) -> int:
    """Process ``/rewind`` in sync REPL. Returns 0 on handled."""
    ref = parse_rewind_args(line)
    assert ref is not None
    thread_id = str((config.get("configurable") or {}).get("thread_id") or "")
    if not thread_id:
        print("ERROR: /rewind requires a thread_id session", file=sys.stderr)
        return 1
    try:
        rows = list_checkpoints(graph, thread_id, completed_only=completed_only)
        if ref == "":
            print(format_checkpoint_table(rows))
            print(
                "Usage: /rewind <index|checkpoint_id>  (forks a NEW thread_id)"
            )
            return 0
        cid = (
            resolve_checkpoint_ref(rows, ref).checkpoint_id
            if ref.isdigit()
            else ref
        )
        fork_cfg = fork_from_checkpoint(
            graph,
            source_thread_id=thread_id,
            checkpoint_id=cid,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _apply_fork_config(config, fork_cfg)
    new_tid = config["configurable"]["thread_id"]
    short = cid if len(cid) <= 13 else cid[:13] + "…"
    print(f"Forked from {short} → thread_id={new_tid} (source tip unchanged)")
    return 0


async def _handle_rewind_async(
    graph,
    config: dict,
    line: str,
    *,
    completed_only: bool,
) -> int:
    ref = parse_rewind_args(line)
    assert ref is not None
    thread_id = str((config.get("configurable") or {}).get("thread_id") or "")
    if not thread_id:
        print("ERROR: /rewind requires a thread_id session", file=sys.stderr)
        return 1
    try:
        rows = await alist_checkpoints(
            graph, thread_id, completed_only=completed_only
        )
        if ref == "":
            print(format_checkpoint_table(rows))
            print(
                "Usage: /rewind <index|checkpoint_id>  (forks a NEW thread_id)"
            )
            return 0
        cid = (
            resolve_checkpoint_ref(rows, ref).checkpoint_id
            if ref.isdigit()
            else ref
        )
        fork_cfg = await afork_from_checkpoint(
            graph,
            source_thread_id=thread_id,
            checkpoint_id=cid,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _apply_fork_config(config, fork_cfg)
    new_tid = config["configurable"]["thread_id"]
    short = cid if len(cid) <= 13 else cid[:13] + "…"
    print(f"Forked from {short} → thread_id={new_tid} (source tip unchanged)")
    return 0


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


def _resolve_slash_prompt(
    prompt: str,
    slash_registry: dict[str, dict[str, str]],
    plugins: list[PluginPack],
) -> tuple[str | None, int]:
    """Expand slash / handle list+pick. Returns (prompt_or_None, exit_code).

    ``None`` prompt means the caller should exit with the given code (list/pick done
    or error already printed).
    """
    try:
        dispatch = dispatch_slash_input(prompt, slash_registry, plugins=plugins)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None, 1
    if dispatch.kind == "list":
        print(dispatch.list_text)
        return None, 0
    if dispatch.kind == "pick":
        print(dispatch.list_text)
        if not dispatch.pick_choices:
            return None, 0
        if not sys.stdin.isatty():
            print(
                "ERROR: /pick requires an interactive TTY "
                "(or call /command directly). Non-interactive: use /help.",
                file=sys.stderr,
            )
            return None, 1
        try:
            selection = read_tty_line("Number: ").strip()
        except EOFError:
            print("ERROR: no pick selection", file=sys.stderr)
            return None, 1
        try:
            expanded = resolve_pick_selection(
                slash_registry, selection, args=dispatch.prompt
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return None, 1
        return expanded, 0
    return dispatch.prompt, 0


async def _run_once_async(
    graph,
    prompt: str,
    config: dict,
    *,
    stream: bool,
    plan_mode: bool,
    slash_registry: dict[str, dict[str, str]],
    plugins: list[PluginPack],
    usage_acc: UsageAccumulator | None,
    use_sync: bool,
) -> int:
    prompt, code = _resolve_slash_prompt(prompt, slash_registry, plugins)
    if prompt is None:
        return code

    # Plan Mode has no ask interrupts — token streaming is fine.
    if stream and plan_mode:
        try:
            if use_sync:
                consume_agent_stream(graph, prompt, config)
            else:
                await consume_agent_astream(graph, prompt, config)
            if usage_acc is not None:
                print(usage_acc.format_footer(), file=sys.stderr)
            return 0
        except Exception as exc:  # noqa: BLE001
            print(
                f"ERROR: agent run failed: {format_run_error(exc)}",
                file=sys.stderr,
            )
            return 1

    if stream and not plan_mode:
        print(
            "Note: HITL ask uses ainvoke + interrupt (not token stream). "
            "Use --plan for stream-only read sessions.",
            file=sys.stderr,
        )

    if use_sync:
        result, code = invoke_with_hitl(graph, prompt, config)
    else:
        result, code = await ainvoke_with_hitl(graph, prompt, config)
    if code != 0:
        return code
    if result and "messages" in result:
        _print_transcript(result["messages"])
    else:
        print("=== done ===")
    if usage_acc is not None:
        print(usage_acc.format_footer(), file=sys.stderr)
    return 0


def _run_once(
    graph,
    prompt: str,
    config: dict,
    *,
    stream: bool,
    plan_mode: bool,
    slash_registry: dict[str, dict[str, str]],
    plugins: list[PluginPack],
    usage_acc: UsageAccumulator | None,
    use_sync: bool = False,
) -> int:
    """Sync entry for ``--sync`` path; opens a nested event loop per turn."""
    return asyncio.run(
        _run_once_async(
            graph,
            prompt,
            config,
            stream=stream,
            plan_mode=plan_mode,
            slash_registry=slash_registry,
            plugins=plugins,
            usage_acc=usage_acc,
            use_sync=use_sync,
        )
    )


def _run_repl(
    graph,
    config: dict,
    *,
    stream: bool,
    plan_mode: bool,
    slash_registry: dict[str, dict[str, str]],
    plugins: list[PluginPack],
    usage_acc: UsageAccumulator | None,
    use_sync: bool,
    completed_only: bool = True,
) -> int:
    """REPL for sync checkpointer (``--sync``); each turn uses ``asyncio.run``."""
    print("REPL mode — empty line or Ctrl-D to exit. Meta: /rewind")
    while True:
        try:
            line = read_tty_line("you> ").strip()
        except EOFError:
            print()
            break
        if not line:
            break
        if parse_rewind_args(line) is not None:
            code = _handle_rewind_sync(
                graph, config, line, completed_only=completed_only
            )
            if code != 0:
                return code
            continue
        code = _run_once(
            graph,
            line,
            config,
            stream=stream,
            plan_mode=plan_mode,
            slash_registry=slash_registry,
            plugins=plugins,
            usage_acc=usage_acc,
            use_sync=use_sync,
        )
        if code != 0:
            return code
    return 0


async def _run_repl_async(
    graph,
    config: dict,
    *,
    stream: bool,
    plan_mode: bool,
    slash_registry: dict[str, dict[str, str]],
    plugins: list[PluginPack],
    usage_acc: UsageAccumulator | None,
    use_sync: bool,
    completed_only: bool = True,
) -> int:
    """REPL inside one event loop (holds AsyncPostgresSaver for the session)."""
    print("REPL mode — empty line or Ctrl-D to exit. Meta: /rewind")
    while True:
        try:
            line = read_tty_line("you> ").strip()
        except EOFError:
            print()
            break
        if not line:
            break
        if parse_rewind_args(line) is not None:
            code = await _handle_rewind_async(
                graph, config, line, completed_only=completed_only
            )
            if code != 0:
                return code
            continue
        code = await _run_once_async(
            graph,
            line,
            config,
            stream=stream,
            plan_mode=plan_mode,
            slash_registry=slash_registry,
            plugins=plugins,
            usage_acc=usage_acc,
            use_sync=use_sync,
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
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Print token usage summary after the run (also USAGE_REPORT=1).",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Use sync graph.invoke/stream (compat shim). Default is async ainvoke/astream (M22).",
    )
    parser.add_argument(
        "--list-checkpoints",
        action="store_true",
        help="List checkpoint history for --thread-id and exit (M31).",
    )
    parser.add_argument(
        "--fork-from",
        default=None,
        metavar="REF",
        help="Fork from checkpoint index or id onto a new thread_id (M31).",
    )
    parser.add_argument(
        "--fork-thread-id",
        default=None,
        help="Optional target thread_id for --fork-from (default: random UUID).",
    )
    parser.add_argument(
        "--all-checkpoints",
        action="store_true",
        help="Include in-progress snapshots when listing (default: completed/idle only).",
    )
    parser.add_argument(
        "--serial-tools",
        action="store_true",
        help="Force serial tool execution (M32 A/B). Default: parallel fan-out; ask batches always serial.",
    )
    parser.add_argument(
        "--structured-route",
        action="store_true",
        help="M33 sidecar: with_structured_output(RouteDecision) on prompt; print JSON and exit.",
    )
    parser.add_argument(
        "--force-tool",
        default=None,
        metavar="NAME",
        help="M33 sidecar: bind_tools tool_choice=NAME (or none|any); print tool_calls and exit.",
    )
    parser.add_argument(
        "--trace-local",
        default=None,
        metavar="PATH",
        help="M34: append redacted LLM/tool span events to a JSONL file (offline traces).",
    )
    parser.add_argument(
        "--handoff-demo",
        action="store_true",
        help="M35 sidecar: supervisor↔specialist handoff graph (not main ReAct).",
    )
    args = parser.parse_args(argv)

    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    plan_mode = bool(args.plan or settings.agent_plan_mode)
    tool_parallel = bool(settings.tool_parallel) and not bool(args.serial_tools)
    use_sync = bool(args.sync)
    completed_only = not bool(args.all_checkpoints)

    if (
        not args.repl
        and not args.prompt
        and not args.list_checkpoints
        and not args.fork_from
        and not args.structured_route
        and not args.force_tool
        and not args.handoff_demo
    ):
        args.prompt = (
            "Use write_file to create demo.txt with contents hello, then read_file it."
        )

    # M33 sidecars: no ReAct graph / checkpointer.
    if args.structured_route or args.force_tool:
        if args.structured_route and args.force_tool:
            print(
                "ERROR: use only one of --structured-route / --force-tool",
                file=sys.stderr,
            )
            return 1
        if args.handoff_demo:
            print(
                "ERROR: --handoff-demo cannot combine with M33 sidecars",
                file=sys.stderr,
            )
            return 1
        prompt = (args.prompt or "").strip()
        if not prompt:
            print(
                "ERROR: --structured-route / --force-tool require a prompt",
                file=sys.stderr,
            )
            return 1
        print("mini-claude-code M33 sidecar (main ReAct graph not used)")
        print(f"  provider:  {settings.llm_provider}")
        print(f"  model:     {settings.llm_model}")
        print(f"  contrast:  {contrast_blurb()}")
        print()
        llm = create_chat_model(settings)
        try:
            if args.structured_route:
                decision = invoke_structured(llm, RouteDecision, prompt)
                print(decision.model_dump_json(indent=2))
                return 0
            assert args.force_tool is not None
            msg = invoke_forced_tool(
                llm, demo_tools(), args.force_tool, prompt
            )
            name = first_tool_call_name(msg)
            print(f"tool_choice forced: {args.force_tool!r}")
            print(f"first tool_call:    {name!r}")
            print(f"all tool_calls:     {msg.tool_calls!r}")
            if msg.content:
                print(f"content:            {msg.content!r}")
            return 0
        except Exception as exc:  # noqa: BLE001 — CLI surfaces provider errors
            print(f"ERROR: M33 sidecar failed: {exc}", file=sys.stderr)
            return 1

    # M35 handoff sidecar (swarm-lite) — not the product ReAct graph.
    if args.handoff_demo:
        prompt = (args.prompt or "").strip()
        if not prompt:
            print("ERROR: --handoff-demo requires a prompt", file=sys.stderr)
            return 1
        print("mini-claude-code M35 handoff demo (main ReAct graph not used)")
        print(f"  provider:  {settings.llm_provider}")
        print(f"  model:     {settings.llm_model}")
        print(f"  contrast:  {handoff_contrast_blurb()}")
        print()
        llm = create_chat_model(settings)
        try:
            out = run_handoff_demo(llm, prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: M35 handoff failed: {exc}", file=sys.stderr)
            return 1
        print(f"status:         {out.get('status')}")
        print(f"active_agent:   {out.get('active_agent')}")
        print(f"handoff_count:  {out.get('handoff_count')}")
        pad = (out.get("scratchpad") or "").strip()
        if pad:
            print("scratchpad:")
            print(pad)
        print("messages (tail):")
        for m in list(out.get("messages") or [])[-8:]:
            role = type(m).__name__
            content = getattr(m, "content", "")
            print(f"  [{role}] {content!r}")
        return 0

    workspace = resolve_workspace_root(settings)
    plugins = resolve_plugins(settings, workspace_root=workspace)
    try:
        slash_registry = slash_registry_from_plugins(plugins)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Meta slash (/help, /plugins): list only — no checkpointer / graph / Postgres.
    # /pick: numbered picker (may continue into the agent after selection).
    if not args.repl and args.prompt:
        try:
            early = dispatch_slash_input(
                args.prompt, slash_registry, plugins=plugins
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if early.kind == "list":
            print(f"workspace:  {workspace}")
            print(f"plugins:    {len(plugins)} pack(s)")
            print()
            print(early.list_text)
            return 0
        if early.kind == "pick":
            print(f"workspace:  {workspace}")
            print(f"plugins:    {len(plugins)} pack(s)")
            print()
            print(early.list_text)
            if not early.pick_choices:
                return 0
            if not sys.stdin.isatty():
                print(
                    "ERROR: /pick requires an interactive TTY "
                    "(or call /command directly).",
                    file=sys.stderr,
                )
                return 1
            try:
                selection = read_tty_line("Number: ").strip()
            except EOFError:
                print("ERROR: no pick selection", file=sys.stderr)
                return 1
            try:
                args.prompt = resolve_pick_selection(
                    slash_registry, selection, args=early.prompt
                )
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1

    thread_id = args.thread_id
    if args.new_thread:
        thread_id = str(uuid4())
    if args.repl and not thread_id:
        thread_id = str(uuid4())
        print(f"Allocated thread_id={thread_id} for REPL")

    if (args.list_checkpoints or args.fork_from) and not thread_id:
        print(
            "ERROR: --list-checkpoints / --fork-from require --thread-id "
            "(source session).",
            file=sys.stderr,
        )
        return 1

    # Ask/HITL needs a checkpointer. Auto-allocate a thread when not in Plan Mode.
    if (
        not plan_mode
        and not thread_id
        and not args.list_checkpoints
        and not args.fork_from
    ):
        thread_id = str(uuid4())
        print(
            f"HITL ask requires a session; allocated thread_id={thread_id}",
            file=sys.stderr,
        )

    use_checkpoint = bool(thread_id)
    if args.repl and not use_checkpoint:
        print("ERROR: --repl requires a thread id", file=sys.stderr)
        return 1
    if (args.list_checkpoints or args.fork_from) and not use_checkpoint:
        print("ERROR: time-travel requires a checkpointer session", file=sys.stderr)
        return 1

    backend: CheckpointBackend | None = (
        args.checkpointer  # type: ignore[assignment]
        if args.checkpointer
        else None
    )
    stream = not args.no_stream

    print("mini-claude-code agent (FS + shell/git + sessions + stream + HITL)")
    print(f"  provider:     {settings.llm_provider}")
    print(f"  model:        {settings.llm_model}")
    print(f"  workspace:    {workspace}")
    print(f"  runtime:      {'sync (--sync)' if use_sync else 'async (ainvoke/astream)'}")
    print(f"  streaming:    {'on' if stream else 'off (--no-stream)'}")
    print(
        f"  plan_mode:    {'on (mutating tools denied)' if plan_mode else 'off'}"
    )
    print(
        f"  tool_fanout:  {'parallel' if tool_parallel else 'serial'}"
        + (
            f" (max_concurrency={settings.tool_max_concurrency})"
            if settings.tool_max_concurrency
            else ""
        )
        + (" [ask batches always serial]" if tool_parallel else "")
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
    store_kind = resolve_store_backend(settings)
    print(f"  store:        {store_kind} ns={store_namespace(settings)!r}")
    trace_local = (args.trace_local or settings.trace_local_path or "").strip()
    tstatus = tracing_status(local_path=trace_local or None)
    for line in tstatus.banner_lines():
        print(line)
    if args.fork_from:
        print(f"  fork_from:    {args.fork_from}")
    if args.list_checkpoints:
        print("  action:       list-checkpoints")
    if not args.repl and args.prompt:
        print(f"  prompt:       {args.prompt}")
    print(f"  plugins:      {len(plugins)} pack(s)")
    if slash_registry:
        names = ", ".join(f"/{n}" for n in sorted(slash_registry))
        print(f"  slash_cmds:   {names}  (/help to list)")
    print()

    config: dict = {"recursion_limit": DEFAULT_RECURSION_LIMIT}
    usage_acc: UsageAccumulator | None = None
    if args.usage or settings.usage_report:
        usage_acc = UsageAccumulator()
    if thread_id:
        config.setdefault("configurable", {})["thread_id"] = thread_id
    if usage_acc is not None:
        config.setdefault("configurable", {})[USAGE_ACCUMULATOR_KEY] = usage_acc

    config = dict(
        enrich_run_config(
            config,
            settings=settings,
            thread_id=thread_id,
            run_name="mcc-agent",
        )
    )
    trace_handler: JsonlTraceHandler | None = None
    if trace_local:
        trace_handler = JsonlTraceHandler(trace_local)
        config = dict(attach_callbacks(config, trace_handler))

    def _build(checkpointer=None, store=None):
        return build_agent_graph(
            settings=settings,
            checkpointer=checkpointer,
            store=store,
            plan_mode=plan_mode,
            tool_parallel=tool_parallel,
            # Production path: interrupt inside wrap (no stdin ask_callback).
            ask_callback=None,
            usage_accumulator=usage_acc,
        )

    def _close_trace(status: str = "ok") -> None:
        if trace_handler is None:
            return
        extra: dict = {}
        if usage_acc is not None:
            extra["usage_total_tokens"] = usage_acc.total_tokens
            extra["usage_llm_calls"] = usage_acc.llm_calls
        if thread_id:
            extra["thread_id"] = thread_id
        trace_handler.close_run(status=status, extra=extra or None)

    _trace_close_status = {"status": "ok"}

    try:
        # Default async path needs AsyncPostgresSaver (aget_tuple). Sync
        # PostgresSaver + ainvoke raises empty NotImplementedError (M22 gap).
        if use_checkpoint and not use_sync:

            async def _async_session() -> int:
                async with open_async_checkpointer(
                    settings, backend=backend, setup=True
                ) as checkpointer:
                    async with open_async_store(settings, setup=True) as store:
                        graph = _build(checkpointer, store)
                        assert thread_id is not None
                        if args.list_checkpoints:
                            rows = await alist_checkpoints(
                                graph,
                                thread_id,
                                completed_only=completed_only,
                            )
                            print(format_checkpoint_table(rows))
                            return 0
                        if args.fork_from:
                            cid = await _aresolve_fork_checkpoint_id(
                                graph,
                                thread_id,
                                args.fork_from,
                                completed_only=completed_only,
                            )
                            fork_cfg = await afork_from_checkpoint(
                                graph,
                                source_thread_id=thread_id,
                                checkpoint_id=cid,
                                target_thread_id=args.fork_thread_id,
                            )
                            _apply_fork_config(config, fork_cfg)
                            print(
                                f"Forked → thread_id="
                                f"{config['configurable']['thread_id']} "
                                f"(from {cid[:13]}…; source tip unchanged)"
                            )
                            if not args.repl and not args.prompt:
                                return 0
                        if args.repl:
                            return await _run_repl_async(
                                graph,
                                config,
                                stream=stream,
                                plan_mode=plan_mode,
                                slash_registry=slash_registry,
                                plugins=plugins,
                                usage_acc=usage_acc,
                                use_sync=False,
                                completed_only=completed_only,
                            )
                        return await _run_once_async(
                            graph,
                            args.prompt or "",
                            config,
                            stream=stream,
                            plan_mode=plan_mode,
                            slash_registry=slash_registry,
                            plugins=plugins,
                            usage_acc=usage_acc,
                            use_sync=False,
                        )

            return asyncio.run(_async_session())

        if use_checkpoint:
            with open_checkpointer(
                settings, backend=backend, setup=True
            ) as checkpointer:
                with open_store(settings, setup=True) as store:
                    graph = _build(checkpointer, store)
                    assert thread_id is not None
                    if args.list_checkpoints:
                        rows = list_checkpoints(
                            graph,
                            thread_id,
                            completed_only=completed_only,
                        )
                        print(format_checkpoint_table(rows))
                        return 0
                    if args.fork_from:
                        cid = _aresolve_fork_checkpoint_id_sync_list(
                            graph,
                            thread_id,
                            args.fork_from,
                            completed_only=completed_only,
                        )
                        fork_cfg = fork_from_checkpoint(
                            graph,
                            source_thread_id=thread_id,
                            checkpoint_id=cid,
                            target_thread_id=args.fork_thread_id,
                        )
                        _apply_fork_config(config, fork_cfg)
                        print(
                            f"Forked → thread_id="
                            f"{config['configurable']['thread_id']} "
                            f"(from {cid[:13]}…; source tip unchanged)"
                        )
                        if not args.repl and not args.prompt:
                            return 0
                    if args.repl:
                        return _run_repl(
                            graph,
                            config,
                            stream=stream,
                            plan_mode=plan_mode,
                            slash_registry=slash_registry,
                            plugins=plugins,
                            usage_acc=usage_acc,
                            use_sync=True,
                            completed_only=completed_only,
                        )
                    return _run_once(
                        graph,
                        args.prompt or "",
                        config,
                        stream=stream,
                        plan_mode=plan_mode,
                        slash_registry=slash_registry,
                        plugins=plugins,
                        usage_acc=usage_acc,
                        use_sync=True,
                    )

        if use_sync:
            with open_store(settings, setup=True) as store:
                graph = _build(None, store)
                if args.repl:
                    return _run_repl(
                        graph,
                        config,
                        stream=stream,
                        plan_mode=plan_mode,
                        slash_registry=slash_registry,
                        plugins=plugins,
                        usage_acc=usage_acc,
                        use_sync=True,
                    )
                return _run_once(
                    graph,
                    args.prompt or "",
                    config,
                    stream=stream,
                    plan_mode=plan_mode,
                    slash_registry=slash_registry,
                    plugins=plugins,
                    usage_acc=usage_acc,
                    use_sync=True,
                )

        async def _async_no_checkpoint() -> int:
            async with open_async_store(settings, setup=True) as store:
                graph = _build(None, store)
                if args.repl:
                    return await _run_repl_async(
                        graph,
                        config,
                        stream=stream,
                        plan_mode=plan_mode,
                        slash_registry=slash_registry,
                        plugins=plugins,
                        usage_acc=usage_acc,
                        use_sync=False,
                    )
                return await _run_once_async(
                    graph,
                    args.prompt or "",
                    config,
                    stream=stream,
                    plan_mode=plan_mode,
                    slash_registry=slash_registry,
                    plugins=plugins,
                    usage_acc=usage_acc,
                    use_sync=False,
                )

        return asyncio.run(_async_no_checkpoint())
    except ValueError as exc:
        _trace_close_status["status"] = "error"
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        _trace_close_status["status"] = "error"
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        _close_trace(status=_trace_close_status["status"])


if __name__ == "__main__":
    raise SystemExit(main())
