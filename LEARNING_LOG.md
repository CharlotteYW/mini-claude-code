# Learning Log

Dated entries after each completed milestone. Keep entries short; full detail lives in `docs/milestones/`.

---

## 2026-08-20 — M1: Tool-calling parity

- Insight: **Compatibility is LangChain’s job at the boundary** — one `@tool` + `HumanMessage`/`AIMessage`/`ToolMessage`; adapters map to Anthropic vs OpenAI-family wire formats. We do not maintain four schemas in agent code.
- Insight: **`tool_calls` can arrive with empty `content`** (observed on Ollama/`gemma4:31b`). Agent loops must branch on `tool_calls`, not on assistant text.
- Insight: M2 StateGraph **consumes** this normalized message layer; it does not replace it.
- Link: [docs/milestones/M1-tool-calling-parity.md](docs/milestones/M1-tool-calling-parity.md), [docs/notes/tool-calling-parity.md](docs/notes/tool-calling-parity.md)

---

## 2026-08-21 — Process: mandatory unit + integration tests

- Insight: Tests are part of the learning archive — each milestone Plan must list unit + integration cases; Done requires them. M0/M1 owe a testing catch-up before M2.
- Link: [docs/notes/testing.md](docs/notes/testing.md)

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
