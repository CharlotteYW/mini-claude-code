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
| M11 | [Docker sandbox](milestones/M11-docker-sandbox.md) | **Done.** `run_shell` via ephemeral Docker; `SHELL_BACKEND=host` opt-in; `git_*` stay host. |

## Tier 3 — Extensibility

| ID | Title | Goal |
|---|---|---|
| M12 | [Sub-agents](milestones/M12-sub-agents.md) | **Done.** YAML child agents; isolated context; `run_subagent`; same model. |
| M13 | [Skills (progressive disclosure)](milestones/M13-skills-progressive-disclosure.md) | **Done.** Catalog always on; `load_skill` loads full body; vs M12 subagents. |
| M14 | [MCP client](milestones/M14-mcp-client.md) | **Done.** Adapter merges stdio MCP tools into ToolNode; in-repo echo_math demo; opt-in config. |
| M15 | [Lifecycle hooks](milestones/M15-lifecycle-hooks.md) | **Done.** PreToolUse / PostToolUse / Stop in policy plane; demo handlers; topology unchanged. |
| M16 | [Plugins & slash commands](milestones/M16-plugins-slash-commands.md) | **Done.** Plugin packs, `/review`, `/help` discovery, hook merge; topology unchanged. |

## Tier 4 — Optional

| ID | Title | Goal |
|---|---|---|
| M17 | [Eval harness & cost/retry](milestones/M17-eval-harness-cost-retry.md) | **Done.** Eval cases + `mcc-eval`, LLM retry/backoff, `--usage` token footer. |
| M18 | [Slack OAuth → agent → open PR](milestones/M18-chat-channel-open-pr.md) | **Done.** Slack OAuth + Socket Mode; `open_pull_request` via `GH_TOKEN`; M19 gate deferred. |
| M19 | [Pre-ship quality gate](milestones/M19-pre-ship-quality-gate.md) | **Done.** `ship_check` (ruff + unit tests); gate `open_pull_request`; optional `git_push` when `SHIP_MODE=push`. |
| M20 | [Doc ingestion & memory pipeline](milestones/M20-doc-ingestion-memory-pipeline.md) | **Done.** Chunk/clean/metadata ingest → pgvector `memory_chunks` + Neo4j Document/Chunk; `ingest_docs` / `search_chunks`. |
| M21 | [Elasticsearch (local full-text)](milestones/M21-elasticsearch-fulltext.md) | **Done.** Compose ES; `search_keyword` BM25; triple-write ingest with M20 chunks. |
| M22 | [Async agent runtime](milestones/M22-async-agent-runtime.md) | **Done.** Default `ainvoke`/`astream`; permission/hook coroutines; MCP sync shim demoted. |
| M23 | [Plugin pack expansion (skills / MCP / subagents)](milestones/M23-plugin-pack-expansion.md) | **Done.** `plugin.yaml` declares skills/MCP/subagents; merge into M13/M14/M12; packs `review`, `docs-mcp`, `research`. |
| M24 | [Plugin hooks & discovery (industry)](milestones/M24-plugin-hooks-discovery.md) | **Done.** Shell/script hook runners (deny-by-default + allowlist); `/pick` numbered slash picker; pack `shell-hooks`. |
| M25 | [Plugin install & trust (local-first)](milestones/M25-plugin-install-trust.md) | **Done.** `mcc-plugins install/list/trust`; versioned manifests; `.trust.yaml` enable + MCP/shell capability flags. |
| M26 | [MCP tool content policy & safety](milestones/M26-mcp-content-policy.md) | **Done.** Content-aware deny for `no-ai` / CONFIDENTIAL; fake docs MCP; client wrap + server policy; contrast M9/M15. |

**M18 learning notes (when we get there):** the bot is an *interface*, not a new graph — same checkpointer sessions as CLI. **Slack OAuth v2** for workspace install (bot token per `team_id`); **GitHub via `GH_TOKEN`** only (no GitHub OAuth in M18). Socket Mode for local dev; dry-run PR default; deny-by-default until M9/M10. Always call through **M19** so channel-triggered ships cannot skip CI-like checks. Reuse M16 `dispatch_slash_input` for messages that start with `/`.

**M19 learning notes (when we get there):** this is an *agentic quality loop*, not “hope the human ran pytest.” Wire `./scripts/test.sh` (+ formatter, e.g. ruff/black once chosen) as tools or a single `ship_check` tool; treat red tests as recoverable errors in the ReAct loop. Cap iterations to avoid infinite spend. **Simplification:** local checks only first (no mandatory GitHub Actions wait); production would also require remote CI status. Owner-push is a policy switch (`SHIP_MODE=pr|push`) with HITL confirmation from M9/M10 — never silent force-push.

**M20 learning notes (when we get there):** “Neo4j does chunking” is a common mix-up — **chunking/cleaning is an ingestion pipeline**; Neo4j *stores* the resulting entities/chunks/edges. Pipeline should be store-agnostic enough to also feed pgvector (and later ES). Keep runnable on Docker Desktop; no cloud-only deps. Still a learning repo: label what real multi-tenant prod would still need (ACL, job queue, evals).

**M21 learning notes (when we get there):** ES complements, does not replace, Neo4j or pgvector — keyword/full-text at scale vs relations vs semantic similarity. Add as another Compose service (local). Agent gets search tools; document the three-way choice. Optional: hybrid later (ES filter + vector re-rank) as a dig after M20/M21.

**M22 learning notes (when we get there):** M14 kept a **sync** ReAct/CLI path and wrapped MCP tools with `asyncio.run(ainvoke)` so ToolNode/permissions keep working. Production-shaped runtimes usually stay async end-to-end (`ainvoke` / `astream`, async tool execution, HITL resume without nested event loops). Goal: remove `wrap_mcp_tool_for_sync` as the default path; keep sync only as a thin compatibility shim if needed. Pair with optional digs: stateful `client.session(...)`, MCP HTTP transport. Do **not** replace MCP with plain local `@tool` demos — that drops the protocol lesson.

**M23 learning notes (when we get there):** M16 plugins = slash + hook **id** merge only. Industry packs often also ship **skills** (playbooks), **MCP** (stdio/HTTP entries), and **subagent** defs. Teach merge semantics: plugin declares → runtime registers into the same extension planes (skills catalog / `build_default_tools` MCP list / subagent loader) — not new parent nodes. Contrast: slash changes HumanMessage; skills change prompt view; MCP expands tool list; subagents add `run_subagent` targets. **Simplification:** local `workspace/plugins/<id>/` tree with co-located assets; no remote marketplace.

**M24 learning notes (when we get there):** Industry hooks (e.g. Claude Code) often run **shell commands** with JSON stdin/stdout, not only in-process Python ids. Add opt-in runner behind M9/M10 (deny-by-default for mutating shell). Discovery beyond M16 **方案 A**: numbered picker or TUI — still CLI boundary, not graph nodes. Optional **SessionStart** / **UserPromptSubmit** hooks as extension-plane dig if they clarify lifecycle without graph bloat.

**M25 learning notes (when we get there):** Production plugins imply **trust**: signed packages, permission prompts, scoped MCP/network. Learning repo: `mcc plugins install ./path` or git clone into `workspace/plugins/`; manifest `version` + `requires`; block unknown hook runners until allowlisted. Label what a real marketplace still needs (signing, updates, org policy). Do not silently auto-load arbitrary Python from plugin paths (M16 deliberately avoided this).

**M26 learning notes (when we get there):** M9 answers “may this *tool* run?” (auto/ask/deny). M15 hooks can audit/block by *name/args*. M26 teaches **content-aware policy**: after (or before) an MCP read, inspect title / first line / metadata for markers like `no-ai` / `CONFIDENTIAL` and return a deny string so the model never sees the body. Teaching demo: in-repo fake “docs” MCP (or fixture files) — **not** live Google Docs OAuth unless opted in. Contrast **server-enforced** policy (MCP server refuses) vs **client wrap** after `get_tools` (our agent cannot trust a hostile server). Prefer fail-closed; label that real Google Docs needs Drive API + shared labels/ACLs, not only a first-line convention.
## Status legend

Milestone files use: `Planned` / `In Progress` / `Done`. Only M0 has a full Plan doc so far; later files are created when we enter that milestone.
