# Milestone 27: Hybrid retrieval (ES → vector)

## Status

Planned

## Goal

Keyword / BM25 stage (Elasticsearch) then semantic re-rank (pgvector) over the **same chunk ids**; expose one `search_hybrid` (or equivalent) tool and document when hybrid beats solo `search_keyword` / `search_chunks`.

## Why this milestone

M20/M21 taught three stores in isolation. Production RAG usually **combines** exact-token filters with embedding similarity. Teach staged retrieval without hiding it behind a magic “search everything” tool.

## Concepts introduced

- Filter-then-embed vs reciprocal rank fusion (pick one primary design)
- Shared `chunk_id` space across ES and pgvector
- Agent-visible two-stage tool contract

## Design decisions & alternatives considered

| Decision | Tentative choice | Alternatives |
|---|---|---|
| Fusion | ES top-k → vector re-rank on candidates | RRF of two lists; cross-encoder (later dig) |
| Tool surface | One `search_hybrid` + keep solo tools | Replace solo tools (loses teaching contrast) |

## Architecture graph (planned)

```mermaid
flowchart LR
  Q[query] --> ES[search_keyword / ES filter]
  ES --> IDs[candidate chunk_ids]
  IDs --> V[pgvector re-rank]
  V --> Out[cited chunks]
```

## Testing (planned)

### Unit

- [ ] Hybrid merge / re-rank pure function with fake scores
- [ ] Empty ES → graceful fallback or empty (documented)

### Integration

- [ ] Ingest fixture → hybrid hit contains required token and ranks semantic peer (skip if ES/Postgres down)

## Tasks

- [ ] Plan detail + approve
- [ ] Implement tool + wire ingest ids
- [ ] Unit + integration; Results + LEARNING_LOG; commit + push

## Demo / acceptance criteria

1. Query that needs both a rare token and paraphrase still ranks the right chunk.
2. Docs explain when to call hybrid vs solo tools.

## Results

_(fill after implementation)_
