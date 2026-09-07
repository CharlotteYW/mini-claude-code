# Milestone 27: Hybrid retrieval (ES → vector)

## Status

Done

## Goal

Add **`search_hybrid`**: stage-1 Elasticsearch BM25 / keyword candidates, then stage-2 **pgvector re-rank** on the **same logical chunks** joined by `(doc_id, chunk_index)`. Keep `search_keyword` and `search_chunks` as solo tools for teaching contrast. Document when hybrid beats either alone.

## Why this milestone

M20/M21 taught three stores in isolation. Production RAG usually needs **exact token** (must contain `ORBIT-9`) **and** semantic closeness. Hybrid makes that staged and visible — not a magic “search everything” tool.

## Concepts introduced

- **Filter-then-embed** (primary design): ES top-k → restrict → vector re-rank
- Shared **logical** chunk key: `{doc_id}:{chunk_index}` (ES `_id`); pgvector joins via `UNIQUE(doc_id, chunk_index)` (UUID PK is **not** the join key)
- Agent-visible two-stage contract
- Empty ES → empty hybrid (no silent global vector fallback)

## Design decisions & alternatives considered

| Decision | Choice | Alternatives |
|---|---|---|
| Fusion | **ES top-k → pgvector re-rank on candidates** | RRF of two full lists (defer); cross-encoder (later dig) |
| Join key | `(doc_id, chunk_index)` | Pretend ES `_id` == pgvector `id` (**wrong**) |
| Tool surface | New `search_hybrid` + keep solos | Replace solos (loses teaching contrast) |
| Empty ES | Explicit empty | Fall back to pure `search_chunks` (hides lesson) |
| Topology | No new graph nodes; tool only | Extra retrieval node |

**Simplification:** no RRF, no cross-encoder. Candidate pool `k_es = min(40, max(limit * 4, limit))`.

## Architecture graph (planned / as-built)

```mermaid
flowchart LR
  Q[query] --> ES[ES multi_match BM25]
  ES --> Cand["candidates (doc_id, chunk_index)"]
  Cand --> PV[pgvector cosine among keys]
  PV --> Out["cited chunks source_path#index"]
```

ReAct topology **unchanged**.

## Testing (planned)

### Unit

- [x] Key extract / dedupe; re-rank by score
- [x] Empty ES → no `search_chunks_among` call
- [x] Join keys are `(doc_id, chunk_index)` not UUID
- [x] Permission auto; tool registered

### Integration

- [x] Dual-write fixture + bias embedder → hybrid ranks preferred chunk (skip if ES/Postgres down)

## Tasks

- [x] Library `memory/hybrid.py` + `search_chunks_among`
- [x] Tool + permissions
- [x] Unit + integration + `./scripts/m27-demo.sh`
- [x] Results + LEARNING_LOG + architecture; commit + push

## Demo / acceptance criteria

1. Integration proves keyword candidates + vector re-rank order.
2. Tool description states hybrid = ES then vector; solos remain.
3. Unit green; integration present (skip OK without services).

## Results

### What we did

- **`memory/hybrid.py`:** `keys_from_keyword_hits`, `rerank_hits_by_score`, `search_hybrid`.
- **`pgvector_chunks.search_chunks_among`:** cosine search filtered by `(doc_id, chunk_index)` VALUES join.
- **`search_hybrid` tool** in `memory_tools.py`; `READ_SAFE_TOOLS` includes it.
- **`./scripts/m27-demo.sh`**.

### Commands & how to reproduce

```bash
./scripts/test.sh tests/unit/test_m27_hybrid.py -v
./scripts/test.sh tests/integration/test_m27_hybrid_live.py -v
./scripts/m27-demo.sh
```

### As-built graph + delta

Topology **unchanged**. Delta = retrieval tool plane only.

### Why this approach

Forces the join-key lesson (UUID ≠ ES `_id`) and keeps solo tools for contrast.

### Deviations

None material vs Plan.

### Pitfalls

- Using pgvector `id` as hybrid join key silently returns empty / wrong rows.
- Falling back to global `search_chunks` on empty ES hides the hybrid contract.

### Testing results

```
6 passed (unit test_m27_hybrid)
1 passed (integration test_m27_hybrid_live) — 2026-09-07
```

### Open questions / next dig

- M28 neighbor expand; optional RRF dig later.
