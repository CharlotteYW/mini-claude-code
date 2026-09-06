# Mini Claude Code

A learning project: build a **mini Claude Code** with LangGraph — an agent that can read/search/edit a codebase, run shell commands safely, keep multi-turn sessions, and extend via skills / MCP / plugins.

The goal is not a production product. The goal is to understand **every component and middleware**: why it exists, what degrades without it, and what alternatives look like in the industry.

**Status:** Milestones **M0–M26 Done**. Tier 5 depth digs (**M27–M38**) are Planned — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Learning outcomes

By the end of this repo you should be able to:

- Explain LangGraph primitives (StateGraph, checkpointer, interrupt, subgraph) and when to use each
- Navigate the LangChain ecosystem (chat models, tools, MCP adapters) without treating it as a black box
- Design agents with a **thin ReAct core** and a **policy/extension plane** (permissions, HITL, hooks, skills, sub-agents, plugins, content policy)
- Reason about sessions vs long-term memory (checkpointer ≠ Neo4j / pgvector / Elasticsearch)
- Run async-first CLI (`ainvoke` / `astream`) and know when sync checkpointers break that path
- Switch LLM providers via config (Ollama, Anthropic, OpenAI, OpenRouter) and reason about tool-calling differences

## Architecture (high level)

Layered runtime:

- **Core:** thin LangGraph ReAct loop (`call_model` ↔ `ToolNode`) — topology unchanged from early ReAct through M26
- **Around it:** permissions / Plan Mode / HITL, hooks, skills, MCP, plugins + trust, content policy, compaction, memory stores, Docker sandbox
- **Interfaces:** CLI (`chat.sh` / `agent.sh`) and Slack Socket Mode — same graph, not a second agent

Living diagram: [docs/architecture.md](docs/architecture.md). History: [docs/milestones/](docs/milestones/). Study Q&A: [LEARNING_LOG.md](LEARNING_LOG.md).

**One-tool call onion (outer → inner):** Pre hooks → permissions / HITL → tool body (FS / shell / MCP) → content policy on result → Post hooks → `ToolMessage` → model.

## Defaults

| Setting | Value |
|---|---|
| Default LLM provider | `ollama` |
| Default model | `gemma4:31b` |
| Also supported | Anthropic, OpenAI, OpenRouter (config-driven) |
| Sessions / checkpoints | PostgreSQL — default CLI uses `AsyncPostgresSaver`; `--sync` uses sync `PostgresSaver` |
| Vectors / notes | pgvector (`memory_notes`, `memory_chunks`) |
| Graph memory | Neo4j (`Fact`, Document / Chunk + `NEXT`) |
| Full-text | Elasticsearch (`search_keyword` BM25) |
| Shell | Docker sandbox by default (`SHELL_BACKEND=host` opt-in, insecure) |

## Repo layout

```
mini-claude-code/
├── README.md
├── LEARNING_LOG.md
├── .cursor/rules/
├── docs/
│   ├── architecture.md
│   ├── ROADMAP.md
│   ├── notes/testing.md
│   └── milestones/              # M0–M26 Done; M27–M38 Planned stubs
├── backend/                     # uv package + pytest (unit / integration)
├── mcp_servers/                 # echo_math, fake_docs (teaching MCP)
├── workspace/                   # agent cwd + plugin packs
├── docker-compose.yml           # Postgres+pgvector, Neo4j, Elasticsearch
├── outputs/talk-mini-claude-code/  # optional share deck (.pptx)
└── scripts/                     # see Quick start + Testing below
```

## Quick start

```bash
cp .env.example .env          # or let setup create it
./scripts/setup.sh            # Compose + uv sync (+ optional Ollama pull)
./scripts/smoke.sh            # construct LLM client
./scripts/smoke.sh --ping     # optional live invoke
./scripts/parity.sh           # M1: tool-calling parity across providers
```

### Agent CLI

```bash
./scripts/chat.sh                                    # multi-turn REPL (async + Postgres session)
./scripts/chat.sh --thread-id my-session             # resume a thread
./scripts/chat.sh --plan                             # Plan Mode: mutating tools denied
./scripts/agent.sh "Use write_file to create demo.txt with hello, then read it."
./scripts/agent.sh --plan "Create demo.txt with hello"   # expect write denied
./scripts/agent.sh --sync --plan "hi"                # sync runtime shim
./scripts/agent.sh --usage "Say hello in one sentence."
```

### Plugins / policy demos (no or minimal LLM)

```bash
./scripts/m23-demo.sh         # plugin packs merge
./scripts/m24-demo.sh         # shell hooks + /pick
./scripts/m25-demo.sh         # install / trust
./scripts/m26-demo.sh         # fake_docs content policy (no-ai deny)
# Avoid enabling fake_docs twice: either MCP_USE_FAKE_DOCS=1 OR docs-mcp plugin, not both.
```

### Memory / search demos

```bash
./scripts/m20-demo.sh         # doc ingest → pgvector + Neo4j
./scripts/m21-demo.sh         # Elasticsearch keyword search
./scripts/db-inspect.sh
./scripts/db-inspect.sh postgres --thread-id demo-1
```

### Eval / ship / Slack

```bash
./scripts/eval.sh             # M17 fake-LLM eval harness
./scripts/ship-check.sh       # M19: ruff + unit tests (same as ship_check tool)
./scripts/slack.sh install    # OAuth once (needs SLACK_* in .env)
./scripts/slack.sh run        # Socket Mode bot — same graph as CLI
```

Services (after setup): Neo4j Browser http://localhost:7474 · Elasticsearch http://localhost:9200

## Testing

Strategy: [docs/notes/testing.md](docs/notes/testing.md).

| Layer | Marker | Needs |
|---|---|---|
| **Unit** | `-m unit` (default for `./scripts/test.sh`) | Nothing network / Compose |
| **Integration** | `-m integration` | `.env` + Compose / Ollama / keys as applicable; tests **skip** if unavailable |

### Commands (from repo root)

```bash
# All unit tests (default)
./scripts/test.sh
./scripts/test.sh -m unit -v

# Integration (skips OK without services/keys)
./scripts/test.sh -m integration -v

# One file / one test
./scripts/test.sh tests/unit/test_m26_content_policy.py -v
./scripts/test.sh tests/unit/test_m5_checkpointer.py -v
./scripts/test.sh tests/integration/test_m5_checkpointer_live.py -v
./scripts/test.sh tests/integration/test_m26_fake_docs_live.py -v
./scripts/test.sh tests/unit/test_m10_hitl.py::test_format_run_error_empty_str_uses_repr -v

# Equivalent from backend/
cd backend && uv run pytest -m unit -v
cd backend && uv run pytest -m integration -v
```

### Milestone-oriented unit modules (examples)

| Area | Unit module |
|---|---|
| Factory / parity | `test_m0_factory.py`, `test_m1_parity_unit.py` |
| Graph / FS / shell | `test_m2_agent_graph.py`, `test_m3_fs_tools.py`, `test_m4_shell_git.py` |
| Sessions / stream | `test_m5_checkpointer.py`, `test_m6_streaming.py`, `test_cli_tty_line.py` |
| Compact / memory | `test_m7_compaction.py`, `test_m8_memory.py`, `test_m8_pgvector.py` |
| Safety | `test_m9_permissions.py`, `test_m10_hitl.py`, `test_m11_sandbox.py` |
| Extensibility | `test_m12_subagents.py` … `test_m16_plugins.py` |
| Eval / Slack / ship | `test_m17_*`, `test_m18_*`, `test_m19_*` |
| Ingest / ES / async | `test_m20_*`, `test_m21_*`, `test_m22_*` |
| Plugins / policy | `test_m23_*` … `test_m26_content_policy.py` |

Integration twins live under `backend/tests/integration/` (`*_live.py`).

### Pre-ship gate

```bash
./scripts/ship-check.sh       # ruff + unit — what the agent’s ship_check tool runs
```

## Milestone map (short)

| Tier | Range | Focus |
|---|---|---|
| 0–1 | M0–M6 | Env, providers, ReAct, FS/shell, checkpointer, streaming |
| 2 | M7–M11 | Compact, memory, permissions, HITL, Docker sandbox |
| 3 | M12–M16 | Subagents, skills, MCP, hooks, plugins/slash |
| 4 | M17–M26 | Eval, Slack, ship gate, ingest/ES, async, plugin packs/trust, content policy |
| 5 | M27–M38 | Planned depth digs (hybrid retrieval, Store, traces, handoff, …) |

## Collaboration workflow

1. Plan a milestone → wait for explicit **approved** (Plan includes unit + integration tests)
2. Implement one milestone (small, reviewable) **with tests**
3. In chat: **highlight key code** for review and explain **what / why**
4. Fill milestone **Results** + `LEARNING_LOG.md` Concept Q&A
5. **Commit and push**; clean tree before the next Plan
6. Stop and wait for the next approval

Details: `.cursor/rules/`.

## Language

- Chat with the mentor: Chinese or English (or mixed)
- All repo artifacts (docs, code, commits, filenames): **English only**
