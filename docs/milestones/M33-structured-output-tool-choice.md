# Milestone 33: Structured outputs & forced tool choice

## Status

Done

## Goal

Teach two **closed-control** surfaces beside free-form ReAct:

1. **Structured output** — `with_structured_output` / Pydantic for decide/route/grade/extract without tool soup.
2. **Forced `tool_choice`** — `bind_tools(..., tool_choice=...)` so the model **must** call a named tool.

Main ReAct graph **unchanged**. Sidecar module + CLI demos.

## Why this milestone

ReAct free-form is flexible and sloppy. Routing, grading, and extraction are more reliable with schemas; “must call X” is more reliable with API `tool_choice` than with prompts alone.

## Concepts introduced

- Structured model output vs tool calling
- `tool_choice` none / any / named
- Pydantic gate after LangChain extract
- Contrast: ReAct / schema / force / skills / subagents

## Design decisions & alternatives considered

| Decision | Choice | Alternatives |
|---|---|---|
| Scope | Sidecar helpers + CLI flags | Rewrite graph to schema-only |
| Schemas | `RouteDecision`, `GradeResult` | Prompt JSON + regex |
| Topology | Unchanged | Front-router node |

## Architecture graph (planned / as-built)

```mermaid
flowchart TB
  subgraph default [Default product path — unchanged]
    CM[call_model] <--> PT[PolicyToolNode]
  end

  subgraph sidecar [M33 sidecar]
    User[CLI --structured-route / --force-tool] --> SO[with_structured_output]
    User --> TC[bind_tools tool_choice]
    SO --> Valid[RouteDecision]
    TC --> Calls[AIMessage.tool_calls]
  end
```

## Testing (planned)

### Unit

- [x] Pydantic validate accept/reject
- [x] Fake `with_structured_output` + validation error
- [x] `tool_choice` plumbing / forced invoke

### Integration

- [x] Live structured + forced `add` (skip if unsupported)

## Tasks

- [x] `agent/structured.py` + CLI + demo
- [x] Tests; Results + LEARNING_LOG; commit + push

## Demo / acceptance criteria

1. Validated structured object — **met**.
2. Forced tool call — **met**.
3. Learning Log contrast — **met**.
4. Topology unchanged; tests green — **met**.

## Results

### What we did

- **`agent/structured.py`:** `RouteDecision` / `GradeResult`; `invoke_structured`; `bind_with_tool_choice` / `invoke_forced_tool`; `validate_model`; contrast blurb.
- **CLI:** `--structured-route`, `--force-tool NAME` (sidecar exit; no graph).
- **Demo:** `./scripts/m33-demo.sh`.

### Commands & how to reproduce

```bash
./scripts/test.sh tests/unit/test_m33_structured.py -v
./scripts/test.sh tests/integration/test_m33_structured_live.py -v
./scripts/m33-demo.sh

# live CLI (provider must support structured / tool_choice):
# mcc-agent --structured-route "Summarize text only; no file edits"
# mcc-agent --force-tool add "Compute 17+25 with the add tool"
```

### As-built graph + delta

Default ReAct **unchanged**. Delta = sidecar only.

### Why this approach

Teach closed contracts without breaking M2–M32 product path.

### Deviations

None material.

### Pitfalls

- Not every Ollama model supports structured/`tool_choice` — integration skips.
- Structured output ≠ tool call (conceptually); some providers implement schema via internal tools.
- Parse failure raises; retry is caller policy.

### Testing results

```
8 passed (unit test_m33_structured)
2 passed (integration test_m33_structured_live) — 2026-09-12
```

### Open questions / next dig

- M34 traces; M35 handoff can consume `RouteDecision`-style schemas.
