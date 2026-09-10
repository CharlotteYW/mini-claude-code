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

## Tier 5 — Depth digs (post–M26)

Core loop + Tier-3 extensibility are in place. These milestones sharpen **agent/LLM-specific** gaps that production systems hit next — not generic app features. One at a time; Plan → approve → ship tests + Results + Learning Log Q&A.

| ID | Title | Goal |
|---|---|---|
| M27 | [Hybrid retrieval (ES → vector)](milestones/M27-hybrid-retrieval.md) | **Done.** `search_hybrid`: ES BM25 candidates → pgvector re-rank on `(doc_id, chunk_index)`; solos kept. |
| M28 | [Graph-neighbor expand (Neo4j NEXT)](milestones/M28-graph-neighbor-expand.md) | **Done.** `expand_chunks`: Neo4j `NEXT` ±N window with `source_path#index` cites; search tools stay island finders. |
| M29 | [MCP HTTP transport & sticky session](milestones/M29-mcp-http-session.md) | **Done.** Streamable HTTP `http_counter` + sticky `client.session`; stdio cold `get_tools` kept for contrast. |
| M30 | [LangGraph Store (cross-thread memory)](milestones/M30-langgraph-store.md) | **Done.** `store_put`/`store_get` via LangGraph Store; checkpointer stays per-`thread_id`; Neo4j/pgvector kept. |
| M31 | [Time-travel & branch sessions](milestones/M31-time-travel-branch.md) | **Planned.** List checkpoints; fork `thread_id` / `checkpoint_id` resume; CLI `/rewind` or `--fork-from`; teach “edit past → new future” without mutating history. |
| M32 | [Parallel tools & fan-out](milestones/M32-parallel-tools-fanout.md) | **Planned.** Concurrent tool execution when the model emits multiple `tool_calls`; optional map-reduce style gather node; measure latency vs serial ToolNode. |
| M33 | [Structured outputs & forced tool choice](milestones/M33-structured-output-tool-choice.md) | **Planned.** `with_structured_output` / JSON schema path for “decide then act”; `tool_choice` force/forbid; when schema beats free-form ReAct chatter. |
| M34 | [Observability traces (LangSmith / OTel)](milestones/M34-observability-traces.md) | **Planned.** Export runs as traces (LangSmith and/or OpenTelemetry); correlate tool spans + token usage; optional minimal web timeline (only if it teaches the trace model). |
| M35 | [Multi-agent handoff (swarm-lite)](milestones/M35-multi-agent-handoff.md) | **Planned.** Beyond M12 parent→child `run_subagent`: peer handoff / supervisor pattern with explicit transfer tool and isolated message views; same checkpointer namespace rules. |
| M36 | [RAG / agent eval quality](milestones/M36-rag-agent-eval-quality.md) | **Planned.** Extend M17 beyond smoke: retrieval hit@k, faithfulness/answer relevance (simple judges), regression fixtures for ingest+search+hybrid. |
| M37 | [Prompt caching & budgeted compaction](milestones/M37-prompt-cache-budget.md) | **Planned.** Provider prompt-cache headers where available; make compaction trigger from *real* token estimates + soft budget; show cost delta in `--usage`. |
| M38 | [Remote CI gate (GitHub Checks)](milestones/M38-remote-ci-gate.md) | **Planned.** After M19 local `ship_check`, optionally wait on GitHub Actions / Checks API before `open_pull_request` merge advice; timeout + HITL. |

**M27 learning notes:** M20/M21 taught three stores alone. Hybrid is the industry default for “must contain token X *and* be semantically close.” Prefer **filter-then-embed** or **RRF** over a opaque “magic search” tool — the agent (and you) should see both stages. Simplification: same `chunk_id` space across ES and pgvector; no cross-encoder re-ranker yet.

**M28 learning notes:** Vector search returns islands; docs are sequences. `NEXT` expand is cheap structure RAG. Keep CONTAINS as emergency only. Do not pretend Neo4j “does chunking.”

**M29 learning notes:** Stdio MCP = spawn per process (fine for demos). HTTP + sticky session teaches connection lifecycle, auth headers, and why tool list can be stale. Keep a tiny in-repo HTTP MCP; label OAuth to third-party SaaS as out of scope unless opted in.

**M30 learning notes:** Students often conflate checkpointer with “memory.” Store is the LangGraph-native cross-thread map; Neo4j facts remain the *semantic* long-term store. Teach when to use which.

**M31 learning notes:** Production debuggers and “try that again from step 3” need checkpoint identity. Fork vs overwrite is the key design choice; never silent history rewrite.

**M32 learning notes:** Many models already emit parallel `tool_calls`; serial execution leaves latency on the table. Fan-out must preserve permission/hook planes and error isolation (one tool fail ≠ kill all).

**M33 learning notes:** ReAct free-form is flexible and sloppy. Structured output is for closed decision surfaces (route, grade, extract). Forced `tool_choice` is for “you must call X now.” Contrast both with skills (prompt) and subagents (context isolation).

**M34 learning notes:** Without traces, agent failures are folklore. Prefer one export path that shows LLM → tool → LLM spans; UI is optional candy. Pair with M17 usage accumulator.

**M35 learning notes:** M12 is hierarchical invoke. Handoff/swarm is *control transfer* between peers (or supervisor). Watch context leakage and infinite ping-pong — hard caps + explicit handoff tool.

**M36 learning notes:** M17 proved the harness exists; quality eval asks “did retrieval help?” Use fixed corpora under `workspace/` and deterministic judges where possible; LLM-as-judge labeled as soft.

**M37 learning notes:** Compaction today is size-heuristic. Budgets + cache-aware system prompts change cost curves. Provider differences (Anthropic cache_control vs OpenAI) are the lesson — abstract thinly.

**M38 learning notes:** Local green ≠ CI green. Teaching the wait/poll/timeout loop without turning the agent into a full CD system. HITL on red remote checks.

## Status legend

Milestone files use: `Planned` / `In Progress` / `Done`. Create the full Plan file when entering that milestone (approve before coding).
