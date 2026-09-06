# Milestone 36: RAG / agent eval quality

## Status

Planned

## Goal

Extend M17 beyond smoke: retrieval **hit@k**, simple faithfulness / answer-relevance checks, regression fixtures for ingest + search (+ hybrid if M27 done).

## Why this milestone

A harness that only checks “did not crash” does not teach quality. Agent builders need retrieval and answer regressions.

## Concepts introduced

- hit@k / MRR-style metrics on fixed corpus
- LLM-as-judge (labeled soft) vs deterministic string checks
- Golden fixtures under `workspace/`

## Design decisions & alternatives considered

| Decision | Tentative choice | Alternatives |
|---|---|---|
| Judges | Deterministic first; optional soft LLM judge | Judge-only (flaky) |
| Scope | Retrieval + one QA case set | Full SWE-bench (out of scope) |

## Architecture graph (planned)

```mermaid
flowchart LR
  Fix[fixtures] --> Ingest[ingest]
  Ingest --> Ret[retrieve]
  Ret --> Metric[hit@k]
  Ret --> Ans[agent answer]
  Ans --> Judge[check / soft judge]
```

## Testing (planned)

### Unit

- [ ] Metric helpers
- [ ] Fixture loader

### Integration

- [ ] Eval run on local corpus (skip without DB/ES as needed)

## Tasks

- [ ] Plan detail + approve
- [ ] Cases + runner extensions
- [ ] Tests; Results + LEARNING_LOG; commit + push

## Demo / acceptance criteria

1. `mcc-eval` (or extension) reports hit@k on golden docs.
2. Regression fails when ingest breaks citations.

## Results

_(fill after implementation)_
