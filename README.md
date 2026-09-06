# Mini Claude Code

A learning project: build a **mini Claude Code** with LangGraph — an agent that can read/search/edit a codebase, run shell commands safely, keep multi-turn sessions, and extend via skills / MCP / plugins.

The goal is not a production product. The goal is to understand **every component and middleware**: why it exists, what degrades without it, and what alternatives look like in the industry.

**Status:** Milestones **M0–M26 Done**. Tier 5 depth digs (**M27–M38**) are Planned — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Learning outcomes

By the end of this repo you should be able to:

- Explain LangGraph primitives (StateGraph, checkpointer, interrupt, subgraph) and when to use each
- Navigate the LangChain ecosystem (chat models, tools, MCP adapters) without treating it as a black box
- Design agents with a **thin ReAct core** and a **policy/extension plane** (permissions, HITL, hooks, skills, sub-agents, plugins, content policy)
- Reason about sessions vs long-term memory (checkpointer ≠ Neo4j/pgvector/ES)
- Switch LLM providers via config (Ollama, Anthropic, OpenAI, OpenRouter) and reason about tool-calling differences

## Architecture (high level)

Layered runtime:

- **Core:** thin LangGraph ReAct loop (`call_model` ↔ `ToolNode`)
- **Around it:** permissions / Plan Mode / HITL, hooks, skills, MCP, plugins + trust, content policy, compaction, memory stores, Docker sandbox, Slack as another UI

Living diagram: [docs/architecture.md](docs/architecture.md). History: [docs/milestones/](docs/milestones/). Study Q&A: [LEARNING_LOG.md](LEARNING_LOG.md).

## Defaults

| Setting | Value |
|---|---|
| Default LLM provider | `ollama` |
| Default model | `gemma4:31b` |
| Also supported | Anthropic, OpenAI, OpenRouter (config-driven) |
| Sessions / checkpoints | PostgreSQL (`AsyncPostgresSaver` default async CLI; `--sync` uses sync saver) |
| Vectors / notes | pgvector (`memory_notes`, `memory_chunks`) |
| Graph memory | Neo4j (`Fact`, Document/Chunk) |
| Full-text | Elasticsearch (`search_keyword`) |

## Repo layout

```
mini-claude-code/
├── README.md
├── LEARNING_LOG.md
├── .cursor/rules/
├── docs/
│   ├── architecture.md
│   ├── ROADMAP.md
│   └── milestones/          # M0–M26 Done; M27–M38 Planned stubs
├── backend/                 # Python (uv) package + tests
├── mcp_servers/             # in-repo MCP demos (echo_math, fake_docs)
├── workspace/               # agent cwd + plugins
├── docker-compose.yml
└── scripts/
    ├── setup.sh / smoke.sh / parity.sh / test.sh
    ├── agent.sh             # one-shot / flags
    ├── chat.sh              # multi-turn REPL
    ├── slack.sh             # Slack OAuth + Socket Mode bot
    └── db-inspect.sh
```

## Quick start

```bash
cp .env.example .env   # or let setup create it
./scripts/setup.sh
./scripts/smoke.sh             # construct LLM client
./scripts/smoke.sh --ping      # optional live invoke
./scripts/parity.sh            # tool-calling parity
./scripts/test.sh              # unit tests
./scripts/test.sh -m integration

# Agent
./scripts/chat.sh              # interactive multi-turn (Postgres session)
./scripts/agent.sh --plan "Create demo.txt with hello"   # Plan Mode: writes denied
./scripts/agent.sh "Use write_file to create demo.txt with hello, then read it."

# Slack (optional; needs SLACK_* in .env)
./scripts/slack.sh install
./scripts/slack.sh run

./scripts/db-inspect.sh
```

Neo4j Browser: http://localhost:7474 · Elasticsearch: http://localhost:9200

## Milestone map (short)

| Tier | Range | Focus |
|---|---|---|
| 0–1 | M0–M6 | Env, providers, ReAct, FS/shell, checkpointer, streaming |
| 2 | M7–M11 | Compact, memory, permissions, HITL, Docker sandbox |
| 3 | M12–M16 | Subagents, skills, MCP, hooks, plugins/slash |
| 4 | M17–M26 | Eval, Slack, ship gate, ingest/ES, async, plugin packs/trust, content policy |
| 5 | M27–M38 | Planned depth digs (hybrid retrieval, Store, traces, …) |

## Collaboration workflow

1. Plan a milestone → wait for explicit **approved** (Plan includes unit + integration tests)
2. Implement one milestone (small, reviewable) **with tests**
3. In chat: **highlight key code** for review and explain **what / why**
4. Fill milestone **Results** + `LEARNING_LOG.md` Concept Q&A
5. **Commit and push**; clean tree before the next Plan
6. Stop and wait for the next approval

Testing strategy: [docs/notes/testing.md](docs/notes/testing.md). Details live in `.cursor/rules/`.

## Language

- Chat with the mentor: Chinese or English (or mixed)
- All repo artifacts (docs, code, commits, filenames): **English only**
