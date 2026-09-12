# Milestone 39: Tool observation budgets

## Status

Plan ready — waiting for approval

## Goal

Add a **policy-plane observation budget**: after each tool runs, enforce a unified max size on `ToolMessage` content (head+tail keep, clear truncation marker), optional **summarize-when-huge** for oversized dumps, and a small CLI/stderr signal when truncation fires. Product ReAct topology stays `call_model` ↔ `tools`. Complements M7/M37 (history compact / token budget) which do **not** stop a single `run_shell` / `read_file` from flooding the next prompt.

## Why this milestone

Today truncation is **scattered** (shell/git/fs each have their own `MAX_*` chars). That teaches little about the agent runtime concern: **observations are the #1 context bomber** in coding agents. Industry systems (Claude Code–style) enforce a central ceiling so one bad `cat`/`find` cannot erase the budget you just paid for with compaction and prompt cache.

Without M39: M7/M37 clean history while a single tool result still blows the next `call_model` window.

## Concepts introduced

- **Observation vs transcript** — tool outputs are the hot path into the next LLM call
- **Unified budget** — one policy wrap beats N ad-hoc `MAX_OUTPUT` constants
- **Head+tail truncation** — keep start (errors/headers) + end (results); middle is usually noise
- **Summarize-when-huge** (optional) — lossy second stage when still over budget (**simplification**: same model, no tools)
- Contrast: **M7 compact** = rewrite older *messages*; **M39** = shrink *this* ToolMessage before it joins state

## Design decisions & alternatives considered

| Decision | Choice | Alternatives |
|---|---|---|
| Where | Policy wrap around ToolNode results (PostToolUse-shaped helper) / thin wrap in `PolicyToolNode` or tool wrappers | New graph node; trust each tool forever |
| Default | Char/token estimate budget via env (`TOOL_OBSERVATION_MAX_CHARS`) | Only per-tool constants (status quo) |
| Truncation shape | Head + tail + marker | Head-only; drop entire result |
| Summarize | Opt-in when over 2× budget (`TOOL_OBSERVATION_SUMMARIZE=1`) | Always summarize (slow/costly) |
| Scope | All tools after execute (including MCP) | Shell-only |
| Topology | Unchanged | Dedicated `truncate` node |

## Architecture graph (planned)

```mermaid
flowchart LR
  Tools[PolicyToolNode] --> Obs[observation budget]
  Obs -->|under budget| State[ToolMessage as-is]
  Obs -->|over budget| Trim[head+tail truncate]
  Trim -->|still huge and summarize on| Sum[optional summarize]
  Trim --> State
  Sum --> State
  State --> Model[call_model]
```

Freeze after approval: topology **unchanged**; observation budget is policy-plane like permissions/hooks/M37 cache.

## Testing (planned)

### Unit

- Under budget → unchanged content; no marker.
- Over budget → head+tail present; truncation marker; length ≤ budget (+ marker overhead bound).
- Summarize path: fake summarizer called only when enabled and over threshold; result shorter.
- Wrap applies to a fake tool result string (helper pure functions + one PolicyToolNode / wrap integration-style unit with fakes).

### Integration

- Real `run_shell` or `read_file` producing oversized output under tiny budget → truncated ToolMessage visible in graph state (skip if no workspace; use tmp workspace). No live LLM required if we inject a deterministic long tool; optional Ollama path skip without model.

## Tasks

- [ ] `agent/observation_budget.py` (or `tools/observation.py`) helpers + settings
- [ ] Wire into tool execution path (wrap ToolMessages after tools / PolicyToolNode)
- [ ] Optional summarize hook; stderr/`[obs-budget]` notice
- [ ] Unit + integration tests; `./scripts/m39-demo.sh`
- [ ] Results + LEARNING_LOG + architecture + ROADMAP; commit + push

## Demo / acceptance criteria

1. With a tiny `TOOL_OBSERVATION_MAX_CHARS`, a huge tool dump is truncated before the next model call (marker visible).
2. Docs contrast M7/M37 vs M39 clearly; label summarize-when-huge as simplification.
3. Existing per-tool MAX_* can remain as inner defense; policy plane is the teaching ceiling.

## Results

_(fill after implementation)_
