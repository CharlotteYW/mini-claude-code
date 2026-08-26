# Milestone Roadmap

Learning path for mini Claude Code (LangGraph). One milestone at a time; approve Plan before coding; fill Results (commands, why, graphs) before Done.

Target: understand LangGraph + LangChain ecosystem pieces and be able to design/build agents independently.

## Cross-cutting: tests

Every milestone Plan must include **unit + integration** test cases; Done requires unit tests green and integration tests present (skip if no creds/services). See [notes/testing.md](notes/testing.md).

**Catch-up:** M0 + M1 testing debt **cleared** (`backend/tests/`).

## Tier 0 — Bootstrap / infra

| ID | Title | Goal |
|---|---|---|
| [M0](milestones/M0-environment.md) | Environment & provider skeleton | **Done.** Docker Compose (Postgres+pgvector, Neo4j), `uv` backend, LLM factory for ollama / anthropic / openai / openrouter (default `ollama`+`gemma4:31b`), `setup.sh` / `smoke.sh`. |

## Tier 1 — Core loop & tools

| ID | Title | Goal |
|---|---|---|
| [M1](milestones/M1-tool-calling-parity.md) | LLM provider abstraction & tool-calling parity | **Done.** Same `add` tool across providers via `bind_tools`; Ollama PASS; clouds SKIP without keys; notes on message/`tool_calls` compatibility. |
| [M2](milestones/M2-react-stategraph.md) | Minimal ReAct StateGraph | **Done.** `call_model` ↔ `ToolNode` ReAct loop; `mcc-agent` CLI; MemorySaver optional (not durable). |
| [M3](milestones/M3-filesystem-tools.md) | Filesystem tools | **Done.** read/write/edit/glob/grep with workspace path jail; same ReAct graph. |
| [M4](milestones/M4-shell-git-tools.md) | Shell & git tools | **Done.** `run_shell` + git helpers (subprocess); cwd=workspace; host-insecure until M11. |
| [M5](milestones/M5-postgres-checkpointer.md) | Postgres checkpointer & resume | **Done.** Durable `thread_id` sessions via Postgres checkpointer; MemorySaver for offline/tests; `--repl`. |
| M6 | [Streaming CLI](milestones/M6-streaming-cli.md) | **Done.** Token + tool/node-event streaming; `--no-stream` keeps invoke; frontend still deferred. |

## Tier 2 — Context, memory, safety

| ID | Title | Goal |
|---|---|---|
| M7 | [Context compaction](milestones/M7-context-compaction.md) | **Done.** Auto-summarize past a size threshold; keep recent tail; same ReAct topology. |
| M8 | [Project + long-term memory](milestones/M8-project-long-term-memory.md) | **Done.** `AGENT.md` + Neo4j facts + minimal pgvector notes (`remember_note` / `recall_notes`); M20/M21 parked. |
| M9 | [Permissions & Plan Mode](milestones/M9-permissions-plan-mode.md) | **Done.** Per-tool auto/ask/deny + Plan Mode; ask via CLI stdin (interrupt = M10). |
| M10 | [Human-in-the-loop (`interrupt`)](milestones/M10-human-in-the-loop-interrupt.md) | **Done.** Ask → `interrupt` + `Command(resume=…)`; checkpointer required. |
| M11 | Docker sandbox | Shell/code in ephemeral containers; host subprocess deny-by-default. |

## Tier 3 — Extensibility

| ID | Title | Goal |
|---|---|---|
| M12 | Sub-agents | YAML/Markdown-defined subagents; isolated context; works on all four LLM providers; same model for parent/child first. |
| M13 | Skills (progressive disclosure) | Name+description always in context; full body/scripts on match. |
| M14 | MCP client | Discover/merge MCP tools; dissect adapter → LangGraph tools. |
| M15 | Hooks | PreToolUse / PostToolUse / Stop-style lifecycle hooks. |
| M16 | Plugins & slash commands | Declarative plugin packs + `/command` templates. |

## Tier 4 — Optional

| ID | Title | Goal |
|---|---|---|
| M17 | Eval harness & cost/retry | Tiny evals; retries/backoff; token accounting; optional Anthropic prompt caching. |
| M18 | Chat channel → agent → open PR | Slack and/or Discord bot as a thin adapter: channel message → `thread_id` session → ReAct agent; ship via M19 gate then open PR (or owner push). |
| M19 | Pre-ship quality gate (format + test until green) | Before any PR or push: run formatter + full test suite; on failure, agent keeps editing/re-running until green (bounded retries). Owner may `git push` to the target branch; non-owner / default path opens a PR only. |
| M20 | Doc ingestion + production-ish memory pipeline | Chunking, cleaning, and metadata for project docs/notes; write into Neo4j and/or pgvector with clearer schemas. Local-first “production improvements” (still Compose on a laptop — few users). |
| M21 | Elasticsearch (local Compose) | Add ES (or OpenSearch) to Compose for full-text / keyword search tools beside Neo4j (relations) and pgvector (semantic). Teach when ES wins vs graph vs vectors. |

**M18 learning notes (when we get there):** the bot is an *interface*, not a new graph — same checkpointer sessions as CLI. Opening PRs needs an explicit, permissioned git/GitHub path (M4 deliberately had no `git push`). Prefer one channel first (Discord *or* Slack), dry-run PR creation, and deny-by-default until M9/M10 policy exists. Always call through **M19** so channel-triggered ships cannot skip CI-like checks.

**M19 learning notes (when we get there):** this is an *agentic quality loop*, not “hope the human ran pytest.” Wire `./scripts/test.sh` (+ formatter, e.g. ruff/black once chosen) as tools or a single `ship_check` tool; treat red tests as recoverable errors in the ReAct loop. Cap iterations to avoid infinite spend. **Simplification:** local checks only first (no mandatory GitHub Actions wait); production would also require remote CI status. Owner-push is a policy switch (`SHIP_MODE=pr|push`) with HITL confirmation from M9/M10 — never silent force-push.

**M20 learning notes (when we get there):** “Neo4j does chunking” is a common mix-up — **chunking/cleaning is an ingestion pipeline**; Neo4j *stores* the resulting entities/chunks/edges. Pipeline should be store-agnostic enough to also feed pgvector (and later ES). Keep runnable on Docker Desktop; no cloud-only deps. Still a learning repo: label what real multi-tenant prod would still need (ACL, job queue, evals).

**M21 learning notes (when we get there):** ES complements, does not replace, Neo4j or pgvector — keyword/full-text at scale vs relations vs semantic similarity. Add as another Compose service (local). Agent gets search tools; document the three-way choice. Optional: hybrid later (ES filter + vector re-rank) as a dig after M20/M21.

## Status legend

Milestone files use: `Planned` / `In Progress` / `Done`. Only M0 has a full Plan doc so far; later files are created when we enter that milestone.
