# Architecture (living document)

Current end-to-end picture. Historical planned/as-built graphs live in `docs/milestones/`.

**Last updated:** M5 complete  
**Chosen approach:** Option B — layered runtime

## Goals

Build a mini Claude Code while learning LangGraph + LangChain ecosystem pieces deeply enough to design agents independently after this project.

## Current status (M5)

| Piece | Status |
|---|---|
| ReAct StateGraph | M2 |
| Filesystem tools + path jail | M3 |
| Shell + git tools (host subprocess) | M4 |
| Postgres checkpointer / sessions | **M5 Done** |
| Streaming CLI | Next: M6 |
| Docker sandbox for shell | M11 |

Default tools: `build_default_tools(workspace)` = FS + `run_shell` + `git_*`.  
Sessions: `compile(checkpointer=...)` + `configurable.thread_id` (`CHECKPOINT_BACKEND=postgres|memory`).

## ReAct core (M2–M5)

```mermaid
flowchart LR
  Start([START]) --> CallModel[call_model]
  CallModel -->|tool_calls| Tools[ToolNode]
  CallModel -->|else| EndNode([END])
  Tools --> CallModel
```

**Security note:** `run_shell` sets cwd to the workspace but is **not** a sandbox.

## Message & tool compatibility (M1)

Agent code uses LangChain messages + `AIMessage.tool_calls`. Provider packages adapt wire formats. Details: [notes/tool-calling-parity.md](notes/tool-calling-parity.md).

## Testing (project-wide)

Every milestone ships unit + integration tests. Strategy: [notes/testing.md](notes/testing.md). M0/M1 catch-up tests are in `backend/tests/`.

## Layered runtime (Option B)

```mermaid
flowchart TB
  subgraph ui [Interface]
    CLI[CLI streaming]
  end
  subgraph core [Core ReAct loop - LangGraph StateGraph]
    Model[call_model]
    Tools[tool_executor]
    Model -->|tool_calls| Tools
    Tools -->|ToolMessage| Model
  end
  subgraph plane [Policy and extension plane]
    Perm[Permissions plus Plan mode]
    HITL[interrupt HITL]
    Hooks[Lifecycle hooks]
    Skills[Skills progressive disclosure]
    MCP[MCP tool merge]
    Compact[Context compact]
    Memory[Memory inject]
  end
  CLI --> Compact
  Compact --> Memory
  Memory --> Model
  Tools --> Hooks
  Hooks --> Perm
  Perm --> HITL
  HITL -->|approved| Sandbox[Docker sandbox]
  Sandbox -->|results| Tools
```

### Why this split

| Layer | Responsibility | Without it |
|---|---|---|
| Core ReAct loop | Cognition: model ↔ tools | Manual `while` loops that cannot checkpoint/interrupt cleanly |
| Policy / extension plane | Permissions, hooks, skills, MCP, compaction, memory, sandbox | Every concern becomes another graph node; graph becomes a god-object |

Rejected alternatives:

- **Option A — monolithic StateGraph:** fine for a toy; collapses under Tier-3 mechanisms.
- **Option C — multi-graph from day one:** forces Plan/Execute early but muddies subgraph learning before a working tool loop exists.

## LLM providers

Config-driven factory (no hardcoded vendor in agent code).

| Provider | Default model when selected | LangChain entry | Protocol family |
|---|---|---|---|
| `ollama` (project default) | `gemma4:31b` | `ChatOllama` | Local OpenAI-compatible-ish + Ollama quirks |
| `anthropic` | pin in `.env.example` (e.g. Claude Sonnet) | `ChatAnthropic` | Anthropic Messages API |
| `openai` | pin in `.env.example` | `ChatOpenAI` | OpenAI Chat Completions + tools |
| `openrouter` | any OpenRouter slug | `ChatOpenAI` + OpenRouter `base_url` | OpenAI protocol via gateway |

**Project defaults:** `LLM_PROVIDER=ollama`, `LLM_MODEL=gemma4:31b`.

**Simplification:** one `(provider, model)` pair per run. Per-role multi-model routing is a later optional dig.

Sub-agents (M12) are orchestration in *our* runtime — supported on all four providers if tool calling is reliable. First sub-agent milestone uses the same provider/model for parent and children.

## Infrastructure (M0 landed)

| Concern | Choice | Notes |
|---|---|---|
| Python | `uv` + `pyproject.toml` under `backend/` | `uv sync` via `setup.sh` |
| Sessions / checkpoints | PostgreSQL (`mcc-postgres`) | `PostgresSaver` via `open_checkpointer` (M5); MemorySaver optional |
| Vectors | `pgvector` extension enabled on boot | Unused until embedding search |
| Graph memory | Neo4j Community (`mcc-neo4j`, Browser `:7474`) | Unused until M8 |
| Sandbox | Docker SDK ephemeral containers | M11; host subprocess until then (labeled insecure) |
| Frontend | Deferred | Until streaming/trace visualization helps learning |

## Milestone progress

- **M0 Done** — [milestones/M0-environment.md](milestones/M0-environment.md)
- **M1 Done** — [milestones/M1-tool-calling-parity.md](milestones/M1-tool-calling-parity.md)
- **M2 Done** — [milestones/M2-react-stategraph.md](milestones/M2-react-stategraph.md)
- **M3 Done** — [milestones/M3-filesystem-tools.md](milestones/M3-filesystem-tools.md)
- **M4 Done** — [milestones/M4-shell-git-tools.md](milestones/M4-shell-git-tools.md)
- **M5 Done** — [milestones/M5-postgres-checkpointer.md](milestones/M5-postgres-checkpointer.md)
- Full list: [ROADMAP.md](ROADMAP.md)
