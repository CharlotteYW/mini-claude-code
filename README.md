# Mini Claude Code

A learning project: build a **mini Claude Code** with LangGraph — an agent that can read/search/edit a codebase, run shell commands safely, and complete small coding tasks.

The goal is not a production product. The goal is to understand **every component and middleware**: why it exists, what degrades without it, and what alternatives look like in the industry.

## Learning outcomes

By the end of this repo you should be able to:

- Explain LangGraph primitives (StateGraph, checkpointer, interrupt, subgraph) and when to use each
- Navigate the LangChain ecosystem (chat models, tools, MCP adapters) without treating it as a black box
- Design agent systems with a clear split between the **ReAct core loop** and the **policy/extension plane** (permissions, hooks, skills, sub-agents, plugins)
- Switch LLM providers via config (Ollama, Anthropic, OpenAI, OpenRouter) and reason about tool-calling protocol differences

## Architecture (high level)

We use **Option B — layered runtime**:

- **Core:** thin LangGraph ReAct loop (`call_model` ↔ tool execution)
- **Around it:** permissions, HITL interrupt, hooks, skills, MCP, context compaction, memory, Docker sandbox

See [docs/architecture.md](docs/architecture.md) and the milestone roadmap in [docs/ROADMAP.md](docs/ROADMAP.md).

## Defaults

| Setting | Value |
|---|---|
| Default LLM provider | `ollama` |
| Default model | `gemma4:31b` |
| Also supported | Anthropic, OpenAI, OpenRouter (config-driven) |
| Checkpoint / sessions | PostgreSQL (+ pgvector later) |
| Graph memory (later) | Neo4j |

## Repo layout

```
mini-claude-code/
├── README.md
├── LEARNING_LOG.md
├── .cursor/rules/          # persistent mentor/workflow rules
├── docs/
│   ├── architecture.md
│   ├── ROADMAP.md
│   └── milestones/
├── backend/                # Python (uv) — filled from M0
├── frontend/               # deferred until streaming/trace needs UI
├── docker-compose.yml
└── scripts/
    ├── setup.sh
    └── run.sh
```

## Quick start

```bash
cp .env.example .env   # or let setup create it
./scripts/setup.sh
./scripts/run.sh
./scripts/parity.sh    # M1: tool-calling parity across configured providers
# optional live invoke (needs Ollama + model):
# PULL_OLLAMA_MODEL=1 ./scripts/setup.sh
# ./scripts/run.sh --ping
```

Neo4j Browser: http://localhost:7474 (idle until memory milestones).

## Collaboration workflow

1. Plan a milestone → wait for explicit **approved**
2. Implement one milestone (small, reviewable)
3. In chat: **highlight key code** for review and explain **what / why**
4. Fill milestone **Results** (commands, why, as-built graph) + `LEARNING_LOG.md`
5. **Commit and push** so GitHub stays in sync
6. Stop and wait for the next approval

Details live in `.cursor/rules/`.

## Language

- Chat with the mentor: Chinese or English (or mixed)
- All repo artifacts (docs, code, commits, filenames): **English only**
