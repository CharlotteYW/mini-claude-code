# Learning Log

Dated entries after each completed milestone. Keep entries short; full detail lives in `docs/milestones/`.

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
