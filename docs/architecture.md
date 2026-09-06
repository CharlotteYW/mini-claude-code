# Architecture (living document)

Current end-to-end picture. Historical planned/as-built graphs live in `docs/milestones/`.

**Last updated:** M19 complete  
**Chosen approach:** Option B — layered runtime

## Goals

Build a mini Claude Code while learning LangGraph + LangChain ecosystem pieces deeply enough to design agents independently after this project.

## Current status (M19)

| Piece | Status |
|---|---|
| Core ReAct + tools + sessions + stream | M2–M6 |
| Compact + memory + permissions + HITL + sandbox | M7–M11 |
| Sub-agents / Skills / MCP / Hooks | M12–M15 |
| Plugins & slash / eval / Slack | M16–M18 |
| Pre-ship quality gate | **M19 Done** |

Ship: `ship_check` → fix loop → gated `open_pull_request` (`SHIP_REQUIRE_GREEN`). Optional `SHIP_MODE=push` + `git_push` (ask).

## ReAct core (M2–M11)

```mermaid
flowchart LR
  Start([START]) --> CallModel[call_model]
  CallModel -->|tool_calls| Tools[ToolNode]
  CallModel -->|else| EndNode([END])
  Tools --> CallModel
```

**Security note:** `run_shell` defaults to an ephemeral Docker container (M11). Host backend (`SHELL_BACKEND=host`) is still not a sandbox. M9/M10 ask/deny apply before execution.


## Message & tool compatibility (M1)

Agent code uses LangChain messages + `AIMessage.tool_calls`. Provider packages adapt wire formats. Details: [notes/tool-calling-parity.md](notes/tool-calling-parity.md).

## Testing (project-wide)

Every milestone ships unit + integration tests. Strategy: [notes/testing.md](notes/testing.md). M0/M1 catch-up tests are in `backend/tests/`.

## Layered runtime (Option B)

```mermaid
flowchart TB
  subgraph ui [Interface]
    CLI[CLI streaming]
    Slack[Slack Socket Mode]
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
    Hooks[Lifecycle hooks ids plus shell M24]
    Skills[Skills progressive disclosure]
    MCP[MCP tool merge]
    Plugins[Plugin pack merge M16/M23]
    ContentPolicy[Content policy M26]
    Compact[Context compact]
    Memory[Memory inject]
    Retry[LLM retry backoff]
    Usage[Token usage accounting]
    Ship[ship_check gate]
  end
  subgraph eval [Eval harness outside graph]
    EvalRunner[mcc-eval cases]
  end
  CLI --> Compact
  Slack --> Compact
  Compact --> Memory
  Memory --> Model
  Model --> Retry
  Retry --> Usage
  Tools --> Hooks
  Hooks --> Perm
  Perm --> HITL
  HITL -->|approved| Sandbox[Docker sandbox]
  Sandbox -->|results| ContentPolicy
  ContentPolicy -->|screened ToolMessage| Tools
  Ship -.->|before PR| Tools
```

Note: Content policy also runs **inside** MCP servers that enforce it (e.g. `fake_docs`); the plane node above is the **client wrap** path on returned text.

### Why this split

| Layer | Responsibility | Without it |
|---|---|---|
| Core ReAct loop | Cognition: model ↔ tools | Manual `while` loops that cannot checkpoint/interrupt cleanly |
| Policy / extension plane | Permissions, hooks, skills, MCP, plugins, content policy, compaction, memory, sandbox, ship gate | Every concern becomes another graph node; graph becomes a god-object |

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
| Vectors | `pgvector` + `memory_notes` + `memory_chunks` | M8-B notes; M20 ingest chunks (`doc_id`, path, index) via Ollama embed |
| Graph memory | Neo4j Community (`mcc-neo4j`, Browser `:7474`) | M8 `Fact`; M20 `Document`/`Chunk` + `HAS_CHUNK`/`NEXT` |
| Full-text | Elasticsearch (`mcc-elasticsearch`, `:9200`) | M21: `mcc_chunks` index + `search_keyword` (BM25) |
| Sandbox | Docker SDK ephemeral containers | M11; host subprocess until then (labeled insecure) |
| Frontend | Deferred | Until streaming/trace visualization helps learning |

## Milestone progress

- **M0 Done** — [milestones/M0-environment.md](milestones/M0-environment.md)
- **M1 Done** — [milestones/M1-tool-calling-parity.md](milestones/M1-tool-calling-parity.md)
- **M2 Done** — [milestones/M2-react-stategraph.md](milestones/M2-react-stategraph.md)
- **M3 Done** — [milestones/M3-filesystem-tools.md](milestones/M3-filesystem-tools.md)
- **M4 Done** — [milestones/M4-shell-git-tools.md](milestones/M4-shell-git-tools.md)
- **M5 Done** — [milestones/M5-postgres-checkpointer.md](milestones/M5-postgres-checkpointer.md)
- **M6 Done** — [milestones/M6-streaming-cli.md](milestones/M6-streaming-cli.md)
- **M7 Done** — [milestones/M7-context-compaction.md](milestones/M7-context-compaction.md)
- **M8 Done** — [milestones/M8-project-long-term-memory.md](milestones/M8-project-long-term-memory.md)
- **M9–M19 Done** — permissions through ship gate — see [ROADMAP.md](ROADMAP.md)
- **M20 Done** — [milestones/M20-doc-ingestion-memory-pipeline.md](milestones/M20-doc-ingestion-memory-pipeline.md)
- **M21 Done** — [milestones/M21-elasticsearch-fulltext.md](milestones/M21-elasticsearch-fulltext.md)
- **M22 Done** — [milestones/M22-async-agent-runtime.md](milestones/M22-async-agent-runtime.md)
- **M23 Done** — [milestones/M23-plugin-pack-expansion.md](milestones/M23-plugin-pack-expansion.md)
- **M24 Done** — [milestones/M24-plugin-hooks-discovery.md](milestones/M24-plugin-hooks-discovery.md) (M25 parked; M26 Done earlier)
- **M26 Done** — [milestones/M26-mcp-content-policy.md](milestones/M26-mcp-content-policy.md)
- Full list: [ROADMAP.md](ROADMAP.md)
