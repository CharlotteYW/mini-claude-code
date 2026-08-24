# Learning Log

Dated entries after each completed milestone. Keep entries short; full detail lives in `docs/milestones/`.

**Order: newest first** (reverse chronological). Always prepend new entries below this note.

---

## 2026-08-23 — Future dig parked: Slack/Discord → open PR (M18)

- Idea: use Slack or Discord as the command surface; agent runs in a durable `thread_id` session; end state is opening a GitHub PR — same core graph, new *adapter* layer.
- Why it fits: M5 sessions already answer “continuous chat without FastAPI”; M4 git tools stop before push — M18 would add a permissioned PR path (+ HITL).
- Parked as optional **M18** in [docs/ROADMAP.md](docs/ROADMAP.md); not planned in detail until Tier-1–3 priorities land.

---

## 2026-08-23 — DB inspect helper (Postgres + Neo4j)

- Insight: After M5, durable sessions are not magic — LangGraph writes `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` keyed by `thread_id`. Inspecting the DB closes the loop between `--thread-id` demos and storage.
- Insight: Neo4j is intentionally empty until memory milestones; the same inspect command still verifies Compose connectivity.
- Commands: `./scripts/db-inspect.sh`; `./scripts/db-inspect.sh postgres --thread-id demo-1`
- Simplification: metadata only by default — no full blob dumps.

---

## 2026-08-23 — M5: Postgres checkpointer & sessions

- Insight: **Same graph API**, different durability — `MemorySaver` dies with the process; `PostgresSaver` + `thread_id` is a real session.
- Insight: Hold the Postgres connection open for the whole invoke/REPL (`from_conn_string` is a context manager); `setup()` is idempotent bootstrap.
- Commands: `./scripts/test.sh tests/unit/test_m5_checkpointer.py`; durable demo with `--thread-id` across two `agent.sh` processes.
- Link: [docs/milestones/M5-postgres-checkpointer.md](docs/milestones/M5-postgres-checkpointer.md)

---

## 2026-08-23 — M4: Shell & git tools

- Insight: **VCS** = version control (git here). Prefer structured `git_*` tools for clear schemas; keep `run_shell` for the long tail — both still `subprocess`.
- Insight: **cwd ≠ sandbox** — denylist is a teaching brake; real isolation is M11.
- Link: [docs/milestones/M4-shell-git-tools.md](docs/milestones/M4-shell-git-tools.md)

---

## 2026-08-23 — M3: Filesystem tools

- Insight: Coding power is mostly **tool registration + path jail**, not new graph nodes — topology stayed `call_model` ↔ `tools`.
- Insight: Unique `old_str` edits force the model to read before writing, matching how production coding agents keep diffs reviewable.
- Link: [docs/milestones/M3-filesystem-tools.md](docs/milestones/M3-filesystem-tools.md)

---

## 2026-08-23 — M2: Minimal ReAct StateGraph

- Insight: The ReAct loop is just M1’s message cycle with **explicit conditional edges**; LangGraph’s value is the runtime hook points (checkpointer/interrupt/stream/subgraph), not “tools magic.”
- Insight: Prefer routing on `AIMessage.tool_calls`, not assistant text — empty content on tool turns is normal.
- Pitfall: newer `ToolNode` wants graph runtime — don’t unit-test it with bare `.invoke` outside a compiled graph.
- Link: [docs/milestones/M2-react-stategraph.md](docs/milestones/M2-react-stategraph.md)

---

## 2026-08-21 — Testing catch-up (M0 + M1)

- Insight: Unit tests pin factory/protocol branching and fake-LLM parity without network; integration tests document live contracts and skip cleanly without keys/services.
- Commands: `cd backend && uv run pytest -m unit` (12 passed); `uv run pytest -m integration` (4 passed, 2 skipped without cloud keys).
- Link: [docs/notes/testing.md](docs/notes/testing.md)

---

## 2026-08-21 — Process: mandatory unit + integration tests

- Insight: Tests are part of the learning archive — each milestone Plan must list unit + integration cases; Done requires them. M0/M1 owe a testing catch-up before M2.
- Link: [docs/notes/testing.md](docs/notes/testing.md)

---

## 2026-08-20 — M1: Tool-calling parity

- Insight: **Compatibility is LangChain’s job at the boundary** — one `@tool` + `HumanMessage`/`AIMessage`/`ToolMessage`; adapters map to Anthropic vs OpenAI-family wire formats. We do not maintain four schemas in agent code.
- Insight: **`tool_calls` can arrive with empty `content`** (observed on Ollama/`gemma4:31b`). Agent loops must branch on `tool_calls`, not on assistant text.
- Insight: M2 StateGraph **consumes** this normalized message layer; it does not replace it.
- Link: [docs/milestones/M1-tool-calling-parity.md](docs/milestones/M1-tool-calling-parity.md), [docs/notes/tool-calling-parity.md](docs/notes/tool-calling-parity.md)

---

## 2026-08-20 — M0: Environment & provider skeleton

- Insight: **provider ≠ model ≠ protocol** — OpenRouter reuses `ChatOpenAI`; Anthropic is the odd wire format out. Naming OpenRouter as its own provider documents the gateway pattern instead of hiding it behind a manual `base_url`.
- Insight: **provision vs use** — Neo4j and `pgvector` are healthy in Compose but intentionally unused until checkpoint/memory milestones.
- Pitfall: hatchling forbids `readme` paths outside `backend/`; keep package metadata self-contained.
- Link: [docs/milestones/M0-environment.md](docs/milestones/M0-environment.md)

---

## Template

```markdown
## YYYY-MM-DD — M<N>: <title>

- Insight: ...
- Pitfall: ...
- Link: docs/milestones/M<N>-<slug>.md
```
