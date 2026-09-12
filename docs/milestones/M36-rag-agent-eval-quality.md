# Milestone 36: RAG / agent eval quality

## Status

Done

## Goal

Extend M17 beyond smoke: golden corpus **hit@k**, deterministic faithfulness, `mcc-eval --retrieval`. Product ReAct unchanged.

## Why this milestone

Quality eval asks “did retrieval help?” Fixed corpora + metrics beat folklore.

## Concepts introduced

- hit@k / MRR on cite keys
- qrels / golden fixtures
- Deterministic faithfulness vs soft judge
- Smoke (M17) vs quality (M36)

## Design decisions & alternatives considered

| Decision | Choice | Alternatives |
|---|---|---|
| Surface | `mcc-eval --retrieval` | New graph node |
| Judges | Deterministic first | Judge-only |
| Soft judge | Helper stub (`optional_soft_grade`) | Always-on live |

## Architecture graph (planned / as-built)

```mermaid
flowchart LR
  Fix[evals/corpus + qrels] --> Ingest[ingest_paths]
  Ingest --> Ret[keyword / vector / hybrid]
  Ret --> Hit[hit@k]
  Hit --> Report[mcc-eval --retrieval]
```

## Testing (planned)

### Unit

- [x] Metrics / faithfulness / qrels loader

### Integration

- [x] Golden hit@k keyword + hybrid (bias embedder)

## Tasks

- [x] Corpus + helpers + CLI + tests + docs; commit + push

## Demo / acceptance criteria

1. hit@k reported — **met**.
2. Regression fails when cites break — **met** (failed case surfaces).
3. Learning Log contrast — **met**.

## Results

### What we did

- **`eval/metrics.py`**, **`faithfulness.py`**, **`retrieval.py`**
- Golden **`backend/evals/corpus/`** + **`qrels/rag_smoke.yaml`**
- **`mcc-eval --retrieval [--skip-agent-cases]`**
- **`./scripts/m36-demo.sh`**

### Commands & how to reproduce

```bash
./scripts/test.sh tests/unit/test_m36_rag_eval.py -v
./scripts/test.sh tests/integration/test_m36_rag_eval_live.py -v
./scripts/m36-demo.sh
uv run mcc-eval --retrieval --skip-agent-cases
```

### As-built graph + delta

Product topology **unchanged**. Delta = eval sidecar only.

### Why this approach

Teach retrieval quality beside M17 smoke without RAGAS sprawl.

### Deviations

Soft LLM judge is a reusable helper only (not a default CI case). Hybrid integration uses bias embedder (no Ollama required).

### Pitfalls

- Shared ES/pgvector may show leftover docs from other demos; hit@k still keys on golden cites.
- chunk_index `0` assumes short one-chunk files (our corpus is sized for that).

### Testing results

```
4 passed (unit)
1 passed (integration) — 2026-09-12
mcc-eval --retrieval: 2 passed (keyword + hybrid)
```

### Open questions / next dig

- M37+ per ROADMAP; expand soft-judge CI case if desired.
