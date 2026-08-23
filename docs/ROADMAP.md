# Milestone Roadmap

Learning path for mini Claude Code (LangGraph). One milestone at a time; approve Plan before coding; fill Results (commands, why, graphs) before Done.

Target: understand LangGraph + LangChain ecosystem pieces and be able to design/build agents independently.

## Cross-cutting: tests

Every milestone Plan must include **unit + integration** test cases; Done requires unit tests green and integration tests present (skip if no creds/services). See [notes/testing.md](notes/testing.md).

**Catch-up:** M0 + M1 testing debt **cleared** (`backend/tests/`).

## Tier 0 — Bootstrap / infra

| ID | Title | Goal |
|---|---|---|
| [M0](milestones/M0-environment.md) | Environment & provider skeleton | **Done.** Docker Compose (Postgres+pgvector, Neo4j), `uv` backend, LLM factory for ollama / anthropic / openai / openrouter (default `ollama`+`gemma4:31b`), `setup.sh` / `run.sh`. |

## Tier 1 — Core loop & tools

| ID | Title | Goal |
|---|---|---|
| [M1](milestones/M1-tool-calling-parity.md) | LLM provider abstraction & tool-calling parity | **Done.** Same `add` tool across providers via `bind_tools`; Ollama PASS; clouds SKIP without keys; notes on message/`tool_calls` compatibility. |
| [M2](milestones/M2-react-stategraph.md) | Minimal ReAct StateGraph | **Done.** `call_model` ↔ `ToolNode` ReAct loop; `mcc-agent` CLI; MemorySaver optional (not durable). |
| [M3](milestones/M3-filesystem-tools.md) | Filesystem tools | **Planned.** read/write/edit/glob/grep with workspace path jail; same ReAct graph. |
| M4 | Shell & git tools | Shell + git wrappers; still host subprocess (**temporary insecurity** until sandbox). |
| M5 | Postgres checkpointer & resume | Durable `thread_id` resume; MemorySaver vs Postgres. |
| M6 | Streaming CLI | Token/tool-event streaming; frontend still deferred. |

## Tier 2 — Context, memory, safety

| ID | Title | Goal |
|---|---|---|
| M7 | Context compaction | Auto-summarize past a token threshold. |
| M8 | Project + long-term memory | `AGENT.md`-style inject; Postgres and/or Neo4j facts; when files vs graph vs vectors win. |
| M9 | Permissions & Plan Mode | Per-tool auto/ask/deny + read-only Plan Mode. |
| M10 | Human-in-the-loop (`interrupt`) | LangGraph interrupt for ask-mode tools; policy vs runtime pause. |
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

## Status legend

Milestone files use: `Planned` / `In Progress` / `Done`. Only M0 has a full Plan doc so far; later files are created when we enter that milestone.
