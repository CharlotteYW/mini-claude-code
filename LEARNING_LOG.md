# Learning Log

Dated entries after each completed milestone. Keep entries short; full detail lives in `docs/milestones/`.

**Order: newest first** (reverse chronological). Always prepend new dated entries below the process note / Q&A index.

## Process (standing rule)

1. After a milestone ships and you finish chat review/Q&A → concepts go here (English).
2. Before the next milestone Plan → re-read that milestone’s section in the **Concept Q&A index**; ask remaining questions; then approve the next Plan.
3. Mentor/agent must update this log for review Q&A **without being asked** (Cursor rule: `.cursor/rules/learning-log-qa.mdc`).
4. Milestone **Results** = what we built; this file = **what you understand** (including doubts you had and the answers).

---

## 2026-09-12 — Dig: does this repo auto-run tests on push/PR?

- **Q: After push/PR, do tests run automatically? Do we have Jenkins?**  
  A: **No.** No `.github/workflows`, no Jenkins/Circle/Travis. Quality is **local**: `./scripts/test.sh`, M19 `ship_check`. M38 can *poll* GitHub Checks when they exist, but this learning repo currently has **zero** Actions workflows — remote wait would see empty/pending until CI is added.
- Link: [M38](docs/milestones/M38-remote-ci-gate.md), [M19](docs/milestones/M19-pre-ship-quality-gate.md)

---

## 2026-09-12 — M38: Remote CI gate (GitHub Checks)

- Shipped: `tools/remote_ci.py` (`wait_for_checks` + wrap after `open_pull_request`); HITL on red/timeout; opt-in `SHIP_REMOTE_CI`.
- Insight: **Local green ≠ CI green** — M19 gates laptop checks; M38 polls remote Checks with timeout.
- Insight: Red/timeout must not silently succeed — structured JSON + optional `interrupt` override.
- See Concept Q&A index (M38); Results: [M38](docs/milestones/M38-remote-ci-gate.md).

---

## 2026-09-12 — M37: Prompt caching & budgeted compaction

- Shipped: `prompt_cache.py`; `effective_compact_threshold` + `CONTEXT_TOKEN_BUDGET`; usage cache/budget footer; Anthropic invoke kwargs.
- Insight: Soft budget **tightens** M7 threshold (`min`); prompt cache is **provider-asymmetric** (Anthropic yes, Ollama no-op).
- Insight: Mark the **last leading SystemMessage** (stable prefix), not the whole transcript.
- See Concept Q&A index (M37); Results: [M37](docs/milestones/M37-prompt-cache-budget.md).

---

## 2026-09-12 — Dig: how “did retrieval help?” is judged

- **Q: How do we know retrieval helped?**  
  A: Not by vibes. **Golden corpus** = fixed docs + distractors; **qrels** name the correct `source_path#chunk_index` per query. **hit@k** = 1 iff that cite appears in the top-k ranked list (else 0). **Deterministic faithfulness** = every `required_span` must be a substring of joined evidence texts (no LLM judge). Pass = ranking found the right chunk *and* evidence contains the markers you claimed matter.
- **Q: Golden corpus + hit@k + deterministic faithfulness — what each piece does?**  
  A: Corpus = controllable world (marker doc vs distractor). hit@k = ranking quality metric on cite keys. Faithfulness = grounding check on evidence text (spans ⊆ blob), orthogonal to “was the chunk #1?” Soft LLM judge is optional and flaky — not the CI gate.
- Link: [M36](docs/milestones/M36-rag-agent-eval-quality.md)

---

## 2026-09-12 — M36: RAG / agent eval quality

- Shipped: `eval/metrics.py` + `faithfulness.py` + `retrieval.py`; golden corpus/qrels; `mcc-eval --retrieval`.
- Insight: M17 = smoke harness; M36 = **did retrieval help?** (hit@k on fixed cites).
- Insight: Deterministic faithfulness = required spans ⊆ evidence; soft judge optional/flaky.
- See Concept Q&A index (M36); Results: [M36](docs/milestones/M36-rag-agent-eval-quality.md).

---

## 2026-09-12 — Dig: optional bridge handoff → main ReAct

- **Q: Can handoff results return to the main graph?**  
  A: **Yes, opt-in:** `--handoff-demo --handoff-into-react`. After the sidecar finishes, `bridge_prompt_from_handoff` builds a new user prompt (finish summary + scratchpad + original task) and the CLI **falls through** into normal `build_agent_graph`. Still **two graphs** (not shared state/checkpointer); bridge = prompt relay.
- Link: [M35](docs/milestones/M35-multi-agent-handoff.md)

---

## 2026-09-12 — Dig: handoff demo does not return into main graph

- **Q: After `--handoff-demo`, does the result return to the main ReAct graph?**  
  A: **Default no** (sidecar exit). **Opt-in yes:** `--handoff-into-react` bridges finish/scratchpad into a new main-ReAct prompt (two graphs, prompt relay — not shared thread state).
- Link: [M35](docs/milestones/M35-multi-agent-handoff.md)

---

## 2026-09-12 — Dig: handoff is LLM-decided; demo uses a different graph

- **Q: Is handoff LLM-decided? Does `--handoff-demo` change topology?**  
  A: **Yes, LLM decides** which `handoff_to` / `finish` to call (inside the demo). **`--handoff-demo` does not mutate the product ReAct graph** — it **skips** that graph and runs a **separate** handoff StateGraph. So topology “changes” only in the sense that you are on another map for that command; default `mcc-agent` without the flag still uses `call_model` ⇄ `PolicyToolNode` unchanged.
- Link: [M35](docs/milestones/M35-multi-agent-handoff.md)

---

## 2026-09-12 — Dig: when does handoff actually run

- **Q: When does handoff happen?**  
  A: **Only in the M35 sidecar** — you must run `--handoff-demo` (or call `run_handoff_demo` / the handoff graph in code). Default `mcc-agent` ReAct **never** handoffs. Inside that demo graph, transfer happens when the **current** `active_agent` model emits `handoff_to(...)` (or `finish` to end). Not automatic routing on every user message.
- Link: [M35](docs/milestones/M35-multi-agent-handoff.md)

---

## 2026-09-12 — Dig: topology after M35 + when run_subagent fires

- **Q: Did topology change? When is the subagent called?**  
  A: **Main product graph unchanged** — still `call_model` ⇄ `PolicyToolNode`. M35 is a **separate** sidecar (`--handoff-demo`), not new edges on the product graph. **`run_subagent` (M12)** is a normal tool on the main ToolNode: the model calls it when it decides to (and the tool is in the bound list — workspace `subagents/*.yaml` / plugins). Parent stays in control; child is nested `invoke`, then summary returns. Handoff demo does **not** use `run_subagent`.
- Link: [M12](docs/milestones/M12-sub-agents.md), [M35](docs/milestones/M35-multi-agent-handoff.md)

---

## 2026-09-12 — M35: Multi-agent handoff (swarm-lite)

- Shipped: `handoff.py` supervisor star; `handoff_to`/`finish` via `Command`; `--handoff-demo`; bounce cap + message filters.
- Insight: M12 nested invoke keeps parent in control; M35 **transfers** `active_agent` (different failure mode: ping-pong).
- Insight: Tool `Command` updates must include a matching `ToolMessage` for the `tool_call_id`.
- See Concept Q&A index (M35); Results: [M35](docs/milestones/M35-multi-agent-handoff.md).

---

## 2026-09-12 — Dig: handoff vs subagent (not just another form)

- **Q: Is M35 handoff just a different form of subagent?**  
  A: **Related family, different control contract.** **M12 `run_subagent`** = hierarchical *nested invoke*: parent stays in control, child runs in a tool call, returns a summary, parent continues. **M35 handoff** = *control transfer*: `active_agent` changes; the specialist owns the next turn(s) until it hands back / done. Same “multiple roles” intuition; failure modes differ (nested depth vs ping-pong / context leak). Not “subagent with another API name.”
- Link: [M35 Plan](docs/milestones/M35-multi-agent-handoff.md), [M12](docs/milestones/M12-sub-agents.md)

---

## 2026-09-12 — M34: Observability traces

- Shipped: `tracing.py` (`enrich_run_config`, redact, `JsonlTraceHandler`); CLI banner + `--trace-local`; LangSmith env docs.
- Insight: stream / `--usage` / traces / checkpoints solve different jobs — traces = durable LLM→tool span trees.
- Insight: Topology unchanged; tracing is config + callbacks (sidecar), like M17 usage.
- See Concept Q&A index (M34); Results: [M34](docs/milestones/M34-observability-traces.md).

---

## 2026-09-12 — Dig: how structured.py is invoked

- **Q: How is `structured.py` called?**  
  A: **Not from the ReAct graph.** Sidecar only: (1) CLI `--structured-route` / `--force-tool` early-exit in `cli.py` → `invoke_structured` / `invoke_forced_tool`; (2) tests + `m33-demo.sh` import helpers directly. Default `call_model` ⇄ `PolicyToolNode` never imports it.
- Link: [M33](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — M33: Structured outputs & forced tool choice

- Shipped: `structured.py` (`RouteDecision`, `invoke_structured`, `invoke_forced_tool`); CLI `--structured-route` / `--force-tool`; main ReAct unchanged.
- Insight: Structured out = schema-shaped **data** + Pydantic gate; `tool_choice` = must emit named **tool_call**. Neither removes the model.
- Insight: LangChain orchestrates request/extract then calls Pydantic; retry is optional caller policy.
- See Concept Q&A index (M33); Results: [M33](docs/milestones/M33-structured-output-tool-choice.md).

---

## 2026-09-12 — Dig: BaseModel is Pydantic, not LangChain

- **Q: Is `BaseModel` from LangChain? Why inherit it if Pydantic is its own package?**  
  A: **`BaseModel` is Pydantic’s** (`from pydantic import BaseModel`), not LangChain’s. You subclass it to declare a data model; that’s normal Pydantic usage and works with **zero** LangChain. LangChain *optionally consumes* your Pydantic class (e.g. `with_structured_output(RouteDecision)`). Inheritance is “use Pydantic’s API,” not “depend on LangChain.”
- Docs: [Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/), [Validation](https://docs.pydantic.dev/latest/concepts/models/#validating-data), [JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: what Pydantic is (package vs standard)

- **Q: Is Pydantic a Python package, a function, or an industry standard?**  
  A: **A widely used Python library** (`pip`/`uv` package), not a formal industry standard and not a single function. You define classes subclassing `BaseModel`; methods like `model_validate` run validation. Cross-language “standard” nearby is often **JSON Schema**; Pydantic can emit/consume schema-shaped data. In agents, LangChain/FastAPI etc. commonly use it as the typed gate for structured LLM output and API bodies.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: what Pydantic validation is

- **Q: What is Pydantic validation?**  
  A: Pydantic turns a raw dict/JSON into a typed object **only if** it matches the model’s field types and constraints (`Literal`, required fields, `ge`/`le`, etc.). `model_validate(data)` either returns e.g. `RouteDecision(...)` or raises `ValidationError`. It is **local deterministic checking**, not an LLM call — the gate after structured-output extract.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: who calls model_validate

- **Q: Does LangChain run `RouteDecision.model_validate(data)` after extract?**  
  A: **Yes, when you pass a Pydantic class to `with_structured_output`:** get model reply → extract structured payload → **LangChain invokes Pydantic validation** (conceptually `model_validate`) → return instance or raise. Pydantic still *performs* the check; LangChain *calls* it as the last step of that runnable.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: Pydantic gate vs LangChain orchestration

- **Q: How does Pydantic gate `RouteDecision`? Is LangChain just validate + retry?**  
  A: **Pydantic** = after you have a dict/JSON, `RouteDecision.model_validate(data)` (or parse) checks types, `Literal`s, `Field` bounds; mismatch → `ValidationError` — no object handed to you. **LangChain** does more than validate/retry: pick provider method (json_schema / function-calling / json mode), shape the request, call the model, extract structured payload, then run that Pydantic parse. **Retry is optional** (you or a wrapper may re-invoke on `ValidationError`); it is not “LangChain = only retry.” Default mental model: orchestrate request → parse → validate; retry is a policy you add when you want it.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: who enforces RouteDecision shape — LLM or LangChain?

- **Q: How is output guaranteed to match `RouteDecision` — LLM or LangChain?**  
  A: **Both layers, neither alone is magic.** (1) **Provider/LLM API** (when supported): `response_format` / JSON schema / constrained decoding, or a forced schema-tool — biases or constrains tokens toward that shape. (2) **LangChain `with_structured_output`**: picks a method per provider, parses the reply into Pydantic. (3) **Pydantic validation** locally: accept or raise — this is the hard check in *your* process. If the provider path is weak, you get best-effort + validate/retry, not a mathematical guarantee. Reliability = API constraint + parse/validate (+ optional retry), orchestrated by LangChain, enforced at the boundary by schema validation.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: structured output ≠ function/tool call

- **Q: Does structured output mean the model directly outputs a function call?**  
  A: **Conceptually no.** Structured output = the model’s reply is constrained to a **data schema** (Pydantic/JSON fields like `score`, `mode`). You get a validated **object**, not a ReAct `tool_calls` → ToolNode loop. **Implementation note:** some providers/LangChain paths *internally* use a schema tool / function-calling trick to force JSON — but that is plumbing; your code treats it as `GradeResult(...)`, not “run tool X.” Contrast: **`tool_choice`** = real/agent-visible **must call tool X** with args.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: how structured output / tool_choice make calls more reliable

- **Q: Model normally says “call tool with args abc” — how do we make that more reliable (M33)?**  
  A: Today’s ReAct = `bind_tools(list)` with **default** choice: model *may* chat or call any tool (prompt “please call X” is soft). **Harder contracts:** (1) **`tool_choice="add"`** (or required/any/none) — provider API constrains the *next* completion so it *must* emit that `tool_call` (still model fills args). (2) **`with_structured_output(Schema)`** — next completion must match a JSON/Pydantic shape for decide/grade/extract; often implemented via native `response_format` / json_schema, or *internally* a schema tool — you get a validated object, not a free-form ReAct tool loop. Reliability = API constraint + parse/validate (+ optional retry), not hoping the prompt alone.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-12 — Dig: what M33 is (not “all structure via tools”)

- **Q: Is M33 “future structured output won’t depend on the model; everything comes from tools”?**  
  A: **No.** M33 still depends on the model. It teaches two *closed contracts* beside free ReAct: (1) **`with_structured_output`** — model reply *is* validated Pydantic/JSON (no tool soup); (2) **`tool_choice`** — model *must* emit a named `tool_call` (still the model choosing args / calling). Tool arg schemas already structure *inputs*; M33 structures *outputs* or *forces which tool*. Default ReAct graph stays; sidecar demos only.
- Link: [M33 Plan](docs/milestones/M33-structured-output-tool-choice.md)

---

## 2026-09-11 — Dig: did M32 change graph topology?

- **Q: Did PolicyToolNode change the graph topology vs before?**  
  A: **No.** Still `START → call_model ⇄ tools → (END)`. Only the **implementation** of the `"tools"` node changed (`ToolNode` → `PolicyToolNode` subclass). Same node name, same edges, same ReAct loop. Fan-out is **inside** the tools node, not a new node/edge.
- Link: [M32](docs/milestones/M32-parallel-tools-fanout.md)

---

## 2026-09-11 — Dig: PolicyToolNode is the graph tools node

- **Q: Is PolicyToolNode a ToolNode? How is it invoked when a message arrives?**  
  A: **Yes — subclass of LangGraph `ToolNode`**, registered as the graph’s `"tools"` node. Flow: user `HumanMessage` → `call_model` → if last `AIMessage` has `tool_calls`, router sends state into `"tools"` → `PolicyToolNode` fans out/serializes those calls → returns `ToolMessage`s (gathered) → edge back to `call_model`. It is **not** itself a model-callable tool; it is the **executor node** that runs the tools the model asked for.
- Link: [M32](docs/milestones/M32-parallel-tools-fanout.md)

---

## 2026-09-11 — Dig: where parallel runs vs what wraps each tool

- **Q: Is parallelism in tool_fanout? Does it wrap every tool?**  
  A: **Yes, scheduling is in `PolicyToolNode` (`tool_fanout.py`)** — the graph’s single `"tools"` node. It does **not** wrap each tool’s policy; it **holds the already-wrapped tool list** and runs N `tool_calls` via `executor.map` (sync) or `asyncio.gather` (async). Per-tool wraps (permissions → hooks → content policy) happen **earlier** in `build_agent_graph` / `build_default_tools`. Fan-out = *when* calls run; wraps = *what happens inside each call*.
- Link: [M32](docs/milestones/M32-parallel-tools-fanout.md)

---

## 2026-09-11 — M32: Parallel tools & fan-out

- Shipped: `PolicyToolNode` (`tool_fanout.py`); `TOOL_PARALLEL` / `--serial-tools`; ask-batch → serial; error isolation.
- Insight: LangGraph `ToolNode` already gathered; M32 owns **policy** (measure + HITL safety), not a new executor.
- Insight: Unknown tool names resolve to `ask` → that batch serializes even when parallel is on.
- See Concept Q&A index (M32); Results: [M32](docs/milestones/M32-parallel-tools-fanout.md).

---

## 2026-09-11 — Dig: what “tools fan-out” means

- **Q: What does tools fan-out mean / what does it do?**  
  A: One model turn can emit **several** `tool_calls` on a single `AIMessage` (e.g. read two files at once). **Fan-out** = the runtime **starts those tool bodies concurrently** (async gather / thread pool), then **gathers** the results into multiple `ToolMessage`s before the next `call_model`. Without fan-out (serial), wall time ≈ sum of each tool; with it, wall time ≈ max of independent tools. It is **scheduling inside the `tools` node**, not a new graph topology and not a new product feature. Permissions/hooks still wrap **each** call. Caveat: concurrent **`ask`/HITL** can race — M32 plans to force serial for that batch. Framework note: LangGraph `ToolNode` already fans out; M32 teaches/controls it.
- Link: [M32 Plan](docs/milestones/M32-parallel-tools-fanout.md)

---

## 2026-09-10 — M31: Time-travel & branch sessions

- Shipped: `time_travel.py`; `--list-checkpoints` / `--fork-from`; REPL `/rewind`; fork = new `thread_id` + copy values.
- Insight: M5 resume = tip only; fork grows a **new** future without rewriting history.
- Insight: Do not keep a pinned `checkpoint_id` after fork — `get_state` would freeze on that snapshot.
- See Concept Q&A index (M31); Results: [M31](docs/milestones/M31-time-travel-branch.md).

---

## 2026-09-09 — M30: LangGraph Store

- Shipped: `store_put`/`store_get`; `open_store` / `open_async_store`; `compile(store=…)`; `./scripts/m30-demo.sh`.
- Insight: Checkpointer = per-`thread_id` chat; Store = cross-thread KV (`store` table / InMemory); Neo4j/pgvector stay semantic.
- Insight: Namespace `("mcc","project",id)` must not include `thread_id`.
- See Concept Q&A index (M30); Results: [M30](docs/milestones/M30-langgraph-store.md).

---

## 2026-09-09 — Dig: how cross-session memory sits in the DB

- **Q: How is cross-session memory stored in the database (details)?**  
  A: Several physical stores — same Postgres URL may hold *different* tables for different jobs:
  - **Checkpointer (not cross-thread):** LangGraph tables like `checkpoints` / blobs — keyed by **`thread_id`**. Resume same thread only.
  - **Store (M30):** LangGraph `store` table: `PRIMARY KEY (prefix, key)`, `value jsonb`. `prefix` = joined namespace tuple (e.g. `mcc.project.default`); **no `thread_id` column** — that is why any thread can read. Optional `store_vectors` if indexed search enabled (we plan simple put/get first).
  - **pgvector notes (M8):** our `memory_notes (id, text, embedding vector, created_at)` — cosine search; no thread key.
  - **pgvector chunks (M20):** `memory_chunks` with `doc_id` / `source_path` / `chunk_index` + embedding.
  - **Neo4j Fact (M8):** nodes `(:Fact {id, text, kind, created_at})` — graph DB, not SQL.
  - **AGENT.md:** workspace **file**, not DB.
  Mental model: **thread chat → checkpointer tables; exact KV across threads → `store`; meaning → vectors/graph/file.**
- Link: [M30 Plan](docs/milestones/M30-langgraph-store.md); LangGraph `PostgresStore.setup`

---

## 2026-09-09 — Dig: tell agent to remember → cross-session?

- **Q: If I tell the agent to save something, does that make it cross-session?**  
  A: **Yes — that’s the intended UX**, if the agent actually calls a **durable** write tool:
  - M30: `store_put` → exact KV in Store namespace (any later thread can `store_get`).
  - Already today: `remember_fact` → Neo4j; `remember_note` → pgvector; or you edit `AGENT.md`.
  - **Not** enough: only saying it in chat — checkpointer keeps that only for **this** `thread_id`. New thread won’t see it unless a durable tool (or file) was written.
  Caveats: model must choose the right tool; Plan Mode / deny can block writes; ask-mode may need your approval.
- Link: [M30 Plan](docs/milestones/M30-langgraph-store.md)

---

## 2026-09-09 — Dig: who controls cross-session memory?

- **Q: Who controls how / what gets stored across sessions?**  
  A: **Several controllers, different layers** — not one magic brain:
  1. **You (developer):** choose which primitives exist (checkpointer / Store / Neo4j / pgvector / AGENT.md), namespaces, backends, and whether memory is **tool-visible** vs auto-injected.
  2. **Policy plane (M9/M10):** permissions / Plan Mode / HITL decide if `store_put` / `remember_fact` may run (auto / ask / deny).
  3. **LLM agent (default M30 shape):** *when* to put/get — model chooses tools from descriptions; no silent “save everything.”
  4. **Optional later:** hooks, skills, or a fixed “write memory” graph node (more deterministic, less agent choice).
  5. **Human user:** can instruct “remember X”, approve ask-mode puts, or edit `AGENT.md` directly.
  Teaching default for M30: **dev owns the Store API + namespace; agent owns moment-to-moment put/get; policy can gate writes.**
- Link: [M30 Plan](docs/milestones/M30-langgraph-store.md)

---

## 2026-09-09 — Dig: M30 what crosses sessions?

- **Q: What information is stored across sessions?**  
  A: Depends which layer — they are not the same “memory”:
  - **Checkpointer (M5):** only that **`thread_id`’s transcript** (messages/graph state). New thread → empty chat, even on same Postgres.
  - **Store (M30 Plan):** small **exact KV** under a **project/user namespace** — e.g. prefs, flags, “last chosen package manager”, short structured notes you `store_put`. Visible via `store_get` from **any** thread sharing that namespace. Not a second chat log.
  - **Neo4j Fact (M8):** crisp **project beliefs** you `remember_fact` (ownership, conventions) — semantic/substring recall across threads.
  - **pgvector notes / chunks:** **fuzzy** prose and ingested docs — meaning search across threads.
  - **`AGENT.md`:** always-on **project norms** file — every thread sees it.
  Store does **not** replace the others; it teaches LangGraph’s native cross-thread map for exact keys.
- Link: [M30 Plan](docs/milestones/M30-langgraph-store.md)

---

## 2026-09-09 — Fix: sticky MCP close anyio cancel-scope

- **Q: Why did `./scripts/m29-demo.sh` show a scary traceback on teardown?**  
  A: Streamable HTTP MCP uses **anyio cancel scopes** that must exit in the **same Task** they entered. Old sticky runtime did `run_until_complete(open)` then later `run_until_complete(stack.aclose())` on a different task → `Attempted to exit cancel scope in a different task...`. Fix: one long-lived owner task does open → `await stop` → exit stack, then stops the loop.
- Link: `tools/mcp_sticky.py`

---

## 2026-09-08 — M29: MCP HTTP & sticky session

- Shipped: Streamable HTTP `http_counter`; sticky `client.session` runtime; cold stdio path kept; `./scripts/m29-demo.sh`.
- Insight: Agent stays MCP **client**; HTTP demo is URL-reachable teaching server (localhost default).
- Insight: Cold `get_tools` → new session per call (counter resets); sticky → accumulates.
- See Concept Q&A index (M29); Results: [M29](docs/milestones/M29-mcp-http-session.md).

---

## 2026-09-08 — Dig: M29 “become a real server”?

- **Q: Does M29 MCP hardening mean mini-claude-code becomes a real MCP server?**  
  A: **Mostly no — we stay an MCP *client* (Claude Code shape).** M29 teaches (1) connecting over **HTTP** instead of only stdio spawn, and (2) a **sticky** `client.session(...)` so tool calls reuse one connection. The in-repo Streamable HTTP process is a **tiny demo server** we run so the client path is realistic (stateful counter, headers, lifecycle) — not “ship ourselves as a multi-tenant MCP product.” Stdio servers are already “real” MCP; HTTP makes them reachable like production remote servers. Exposing *our agent* as an MCP server others call would be a different product dig.
- **Q: So our MCP server can be remotely reachable by others?**  
  A: **At the transport level, yes** — Streamable HTTP is URL-addressable (`http(s)://host:port/...`), so *another* MCP client can point at that URL. Stdio is not: the client must spawn your process locally. M29 still defaults to **localhost teaching**; “open on the public internet + auth/OAuth” is deliberately out of scope (headers-only simplification). Remotely reachable ≠ production-hardened SaaS.
- Link: [M29 Plan](docs/milestones/M29-mcp-http-session.md)

---

## 2026-09-07 — M28: Graph-neighbor expand

- Shipped: `expand_chunks` (Neo4j `NEXT` ±N); pure window helpers; `./scripts/m28-demo.sh`.
- Insight: Search finds **islands**; expand supplies **sequence** — keep them separate tools.
- Insight: **Tool plane only** — no new LangGraph node / forced LLM layer (same ReAct).
- See Concept Q&A index (M28); Results: [M28](docs/milestones/M28-graph-neighbor-expand.md).

---

## 2026-09-07 — Dig: M28 = tool plane only?

- **Q: Does M28 only add a tool, with no extra agent/LLM call layer?**  
  A: **Yes (by design).** Same ReAct loop: `call_model` → ToolNode → `call_model`. `expand_chunks` is another **tool** the model may choose after a search hit — not a new LangGraph node, not a forced second LLM, not a subagent. Extra **LLM** turns happen only if the model decides to call expand (then another `call_model` after the tool result), same as any other tool. A dedicated “retrieve then expand” graph node would hide that choice and add a fixed pipeline stage — deferred; M28 teaches **structure RAG as an agent-visible action**.
- Link: [M28](docs/milestones/M28-graph-neighbor-expand.md)

---

## 2026-09-07 — M27: Hybrid retrieval

- Shipped: `search_hybrid` (ES BM25 candidates → pgvector re-rank); `search_chunks_among`; `./scripts/m27-demo.sh`.
- Insight: Join on **`(doc_id, chunk_index)`** — pgvector UUID `id` is not the shared key with ES `_id`.
- Insight: Empty keyword stage → empty hybrid (no silent global vector fallback).
- See Concept Q&A index (M27); Results: [M27](docs/milestones/M27-hybrid-retrieval.md).

---

## 2026-09-05 — Roadmap: Tier 5 planned (M27–M38)

- **Q: After M0–M26, what is still worth learning?**  
  A: Core agent surface is enough to *build*; Tier 5 digs **depth**: hybrid retrieval, graph expand, MCP HTTP/session, LangGraph Store vs checkpointer, time-travel forks, parallel tools, structured output, traces, handoff/swarm, RAG eval quality, prompt cache/budgets, remote CI gate. Listed in [ROADMAP](docs/ROADMAP.md); stub Plans under `docs/milestones/M27`–`M38`.
- Next: skim M26 Q&A in Learning Log if needed; pick one (suggested start: **M27** or **M30**); say ready for a full Plan.

---

## 2026-09-05 — Dig: REPL Chinese backspace leaves first glyph

- **Q: In `chat.sh` REPL, why can I delete only 2 of 3 Chinese characters? English is fine.**  
  A: Cursor/VS Code **xterm** East-Asian width + erase-char is unreliable for CJK (Python readline makes it worse; even a prompt-only line can still fail). English is single-width so it looks fine. Fix: `tty_input.read_tty_line` uses **cbreak + full-line redraw** on each edit — backspace pops a Unicode codepoint and rewrites the line (`\r` + clear), never trusting the terminal to erase double-width glyphs. Optional Cursor setting: `"terminal.integrated.unicodeVersion": "11"`. External Terminal.app is also a valid workaround.
- **Confirmed:** User retested after redraw editor — Chinese delete works.
- Link: `agent/tty_input.py`

---

## 2026-09-05 — Dig: empty REPL error + AsyncPostgresSaver

- **Q: Why did `./scripts/chat.sh` print `ERROR: agent run failed:` with nothing after the colon?**  
  A: Exception was `NotImplementedError()` — **`str(exc)` is empty**. Sync `PostgresSaver` does not implement `aget_tuple`; default CLI after M22 calls `graph.ainvoke` → empty message. Fix: print `repr(exc)` when `str` is blank; use `AsyncPostgresSaver` via `open_async_checkpointer` on the async path.
- **Q: Why did MemorySaver unit tests not catch this?**  
  A: `MemorySaver` implements both sync and async APIs. Only **Postgres sync saver + ainvoke** hits the gap.
- **Q: Why one event loop for the whole REPL?**  
  A: `AsyncPostgresSaver` is an async context manager; holding the connection across turns means `_run_repl_async` inside one `asyncio.run`, not `asyncio.run` per turn (which would close the saver).
- **Q: After fixing the checkpointer, why did MCP break inside async CLI?**  
  A: Graph build still called `load_mcp_tools_sync` → `asyncio.run` while the session loop was already running. Fix: if a loop is running, load MCP in a **worker thread** with its own loop (stdio client stays sync-friendly at assemble time).
- **Q: Why did `ainvoke` succeed then crash on HITL state read?**  
  A: Fallback used sync `graph.get_state` → `AsyncPostgresSaver.get_tuple` forbids sync calls on the main thread. Use `pending_interrupt_values_async` / `aget_state` on the async path.
- Link: `checkpointer.py` (`open_async_checkpointer`), `cli.py`, `hitl.format_run_error`, `mcp_loader.load_mcp_tools_sync`

---

## 2026-09-05 — M25: Plugin install & trust

- Shipped: `mcc-plugins` (install/list/trust/disable); `.trust.yaml`; `version`/`requires`; capability strip for MCP/shell; `./scripts/m25-demo.sh`.
- Insight: **Install ≠ enable.** Presence on disk is not permission to spawn shell hooks or MCP.
- See Concept Q&A index (M25); Results: [M25](docs/milestones/M25-plugin-install-trust.md).

---

## 2026-09-05 — M24: Plugin hooks & discovery

- Shipped: `shell_hooks.py`; script/shell hook entries; `HOOK_SHELL_*`; pack `shell-hooks`; `/pick` picker; `./scripts/m24-demo.sh`.
- Insight: Industry hooks are often **subprocess + JSON**, not only in-process ids — but must be **deny-by-default**.
- See Concept Q&A index (M24); Results: [M24](docs/milestones/M24-plugin-hooks-discovery.md).

---

## 2026-09-05 — M23: Plugin pack expansion

- Shipped: `plugin.yaml` skills/mcp/subagents; merge into M13/M14/M12; packs `review`, `docs-mcp`, `research`; `./scripts/m23-demo.sh`.
- Insight: A plugin is a **bundle that merges into existing planes** — not a new graph node. Slash ≠ skill ≠ MCP ≠ subagent.
- See Concept Q&A index (M23); Results: [M23](docs/milestones/M23-plugin-pack-expansion.md).

---

## 2026-09-05 — Dig: fake_docs purpose + where content_policy runs

- **Q: Is fake_docs mainly a demo?**  
  A: **Yes — a teaching MCP**, not a product docs store. It gives a controllable `read_doc` so you can see **server-enforced** deny vs **client wrap**, without Google OAuth.
- **Q: Does the agent’s content policy only run on the MCP server?**  
  A: **No — two places.** (1) **Server:** `fake_docs.read_doc` imports helpers and denies before returning body. (2) **Client:** `apply_content_policy_wrap` in `build_default_tools` screens results after the tool returns (also `read_file`). Same helpers module; different trust boundary.
- Link: `content_policy.py`, `mcp_servers/fake_docs.py`, `tools/default.py`

---

## 2026-09-05 — Dig: do we have a “real” MCP server?

- **Q: Do we lack a real MCP server?**  
  A: **No — protocol is real.** `echo_math` and `fake_docs` are FastMCP **stdio** servers; the agent loads them via `MultiServerMCPClient` / langchain-mcp-adapters (spawn process, MCP handshake, tools as `BaseTool`). **“Fake” = fake documents**, not fake MCP. What we skip (simplification): third-party marketplace servers, HTTP/SSE as default, long-lived `client.session(...)`, OAuth to Google Docs, etc. You can still point `MCP_CONFIG` at any real stdio/HTTP MCP if you want.
- Link: `mcp_servers/echo_math.py`, `mcp_servers/fake_docs.py`, `tools/mcp_loader.py`

---

## 2026-09-05 — Dig: tool call chain (wrap onion)

- **Q: What is our tool call chain?**  
  A: **Graph:** `call_model` → (if `tool_calls`) `ToolNode` → back to `call_model`. **Build-time onion (outer→inner):** hooks → permissions/HITL → content policy → body (builtin or MCP stdio). **Runtime one call:** Pre hooks → permission auto/ask/deny → (shell may hit Docker sandbox inside body) → tool body → content-policy screens *result* → Post hooks → `ToolMessage` → model. M9/M15 gate *before* body; M26 mainly gates *returned text*. Topology stays two nodes.
- Link: `agent/graph.py`, `permissions.py`, `hooks.py`, `content_policy.py`, `tools/default.py`

---

## 2026-09-05 — M26: MCP content policy

- Shipped: `content_policy.py`; `fake_docs` MCP + fixtures; client wrap on `read_*` / optional `read_file`; `MCP_USE_FAKE_DOCS`; `./scripts/m26-demo.sh`.
- Insight: **Tool ACL ≠ content policy.** M9 allows `read_doc`; M26 still withholds `no-ai` bodies. Client wrap is defense-in-depth; **server-enforced** is the trust boundary.
- See Concept Q&A index (M26); Results: [M26](docs/milestones/M26-mcp-content-policy.md).

---

## 2026-09-05 — M22: Async agent runtime

- Shipped: permission/hook **coroutines**; CLI default `ainvoke`/`astream` + `--sync`; MCP shim flagged; `ainvoke_with_hitl`.
- Insight: The real MCP nested-loop bug was **wraps that only set `func`**, forcing ToolNode back to sync `invoke` → `asyncio.run`. Async CLI alone was not enough.
- See Concept Q&A index (M22); Results: [M22](docs/milestones/M22-async-agent-runtime.md).

---

## 2026-09-05 — M21: Elasticsearch full-text

- Shipped: Compose `mcc-elasticsearch`; `elasticsearch_chunks.py`; triple-write ingest; tool `search_keyword`; `./scripts/m21-demo.sh`.
- Insight: **BM25 answers exact tokens**; cosine answers paraphrase; Neo4j answers structure — three stores, one ingest pipeline. Hybrid re-rank is a later dig.
- See Concept Q&A index (M21) below; Results: [M21](docs/milestones/M21-elasticsearch-fulltext.md).

---

## 2026-09-05 — Dig: Neo4j dual-write is scaffolding for next steps?

- **Q: So Neo4j Document/Chunk (+ edges) is mainly paving the road for later?**  
  A: **Mostly yes.** M20 proves the ingest pipeline can dual-write a graph shape; primary search stays pgvector. Next uses: M21 keyword/ES beside the same chunks; optional digs that *read* `HAS_CHUNK`/`NEXT` (neighbor expand). Plus today’s weak CONTAINS fallback when vectors are down.
- Link: M20 Results / Open questions; ROADMAP M21

---

## 2026-09-05 — Dig: do we actually use Neo4j Document/Chunk after ingest?

- **Q: `search_chunks` uses cosine — is Neo4j used? We store HAS_CHUNK/NEXT but it feels unused.**  
  A: **Correct observation.** Happy path retrieval is **only pgvector**. Neo4j Document/Chunk is used as: (1) **keyword fallback** when embed/Postgres fails (`search_chunks_keyword` = `CONTAINS` on Chunk nodes — does **not** walk `HAS_CHUNK`/`NEXT`); (2) **teaching dual-write** — same pipeline can feed a graph store; (3) **inspectability** (`mcc-db-inspect` / Browser); (4) **scaffold** for later digs (expand neighbors via `NEXT`, entity links). M8 `Fact` is a different Neo4j use (beliefs). **Simplification:** edges are written now, rarely *read* in M20 — intentional, not a hidden ranking feature.
- Link: M20, `memory_tools.search_chunks_tool`, `neo4j_docs.py`

---

## 2026-09-05 — Dig: why not inverted index / BM25 in M20?

- **Q: Why didn’t M20 use inverted index + BM25?**  
  A: M20’s learning target is **dense retrieval** (embed → pgvector cosine) and the **ingest pipeline** (chunk/metadata/dual-write). BM25/inverted index is a **different retrieval family** (keyword/IDF) — parked for **M21 Elasticsearch**, so you can contrast three stores: Neo4j relations, pgvector semantic, ES full-text. Without M20 first, you’d skip “pipeline vs store” and jump to yet another DB. BM25 still wins for exact tokens, rare IDs, boolean filters; vectors win for paraphrase / fuzzy intent. Hybrid (ES filter + vector re-rank) is a later dig.
- Link: M20 `search_chunks`, ROADMAP M21

---

## 2026-09-05 — Dig: where is `search_chunks` and what algorithm?

- **Q: Where is `search_chunks`, what algorithm?**  
  A: **Core:** `memory/pgvector_chunks.py::search_chunks` — embed query with Ollama (`nomic-embed-text`) → pgvector **cosine distance** (`<=>`), order ascending distance, `score = 1 - distance`. **Tool wrap:** `tools/memory_tools.py` (`search_chunks` name); on embed/DB failure falls back to Neo4j `search_chunks_keyword` (case-insensitive `CONTAINS`, not semantic). Not BM25/ES (that’s M21).
- Link: M20, `pgvector_chunks.search_chunks`, `neo4j_docs.search_chunks_keyword`

---

## 2026-09-05 — Dig: M20 mental model (chunk → store → search)

- **Q: Is M20 just “split a doc into chunks, save to DB, search later”?**  
  A: **Yes — that is the core loop.** Extra teaching layers: (1) **pipeline** does clean/chunk/metadata; DBs only store; (2) **dual write** — same chunks → pgvector (semantic) + Neo4j Document/Chunk (structure/keyword); (3) tools `ingest_docs` / `search_chunks` on the existing ReAct graph; (4) not the chat checkpointer — survives new `thread_id`s; (5) still distinct from M8 `remember_fact` / `remember_note`.
- Link: M20, `memory/ingest.py`, `pipeline.py`, `pgvector_chunks.py`, `neo4j_docs.py`

---

## 2026-09-05 — Dig: why is `slack_cli` not under `agent/` like `cli.py`?

- **Q: Why was `slack_cli` at package root instead of `agent/`?**  
  A: Packaging habit, not agent design. Runtime already lived under `agent/` (`slack_bot` / `adapter` / `oauth`); CLI was a thin console entry.
- **Follow-up:** Moved to **`agent/slack_cli.py`**; `mcc-slack = mini_claude_code.agent.slack_cli:main`. Also fixed `.env` discovery depth for both `agent/cli.py` and `agent/slack_cli.py` (`parents[4]` = repo root).
- Link: M18, `agent/slack_cli.py`, `agent/cli.py`, `pyproject.toml` scripts

---

## 2026-09-05 — M20: Doc ingestion & memory pipeline

- Shipped: `memory/ingest.py` + `pipeline.py` + `pgvector_chunks` / `neo4j_docs`; tools `ingest_docs` / `search_chunks`; sample `workspace/docs/`.
- Insight: **Ingestion is a plane outside the graph** — DBs store chunks; they do not invent chunk boundaries. Dual-write teaches vectors (fuzzy) vs graph (Document→Chunk→NEXT) from the **same** pipeline output.
- See Concept Q&A index (M20) below; Results: [M20](docs/milestones/M20-doc-ingestion-memory-pipeline.md).

---

## 2026-09-05 — Parked: M26 MCP content policy (`no-ai` docs)

- User request: learn **tool/MCP safety beyond M9 ACL** — e.g. Google Doc (or demo doc) whose **title or first line** contains `no-ai` → tool returns “cannot read,” body never enters model context.
- Parked as **[M26](docs/ROADMAP.md)** after M19–M25 lane; teaching contrast: M9 tool allow/deny vs **content-aware** client wrap vs server-enforced MCP policy.
- Link: ROADMAP M26 learning notes

---

## 2026-09-05 — Dig: is `slack.sh run` a long-lived listener? vs production

- **Q: Does `./scripts/slack.sh run` mean our agent keeps listening to Slack?**  
  A: **Yes for Socket Mode.** `mcc-slack run` is a **long-lived process**: connect WebSocket → register handler → `Event().wait()` until Ctrl+C. Each inbound message runs the agent (synchronously in M18). Stop the process → no replies.
- **Q: Is enterprise the same?**  
  A: **Same idea (something must be always-on to receive events), different packaging.** Production often: K8s Deployment / systemd service, auto-restart, multiple workers, **ack fast then queue** agent work (Redis/SQS), or Events API behind HTTPS + autoscaling. M18 simplification: one laptop process, agent runs inline on the listener thread.
- Link: M18, `scripts/slack.sh`, `slack_bot.run_socket_mode_bot`

---

## 2026-09-05 — Dig: why both xoxb- and xapp-?

- **Q: When I send a Slack message, I use the OAuth bot token — why also `SLACK_APP_TOKEN`?**  
  A: **Two jobs, two tokens.** `xoxb-` (from OAuth install) = **act as the bot** (read/post/reactions via Web API). `xapp-` (App-Level Token, `connections:write`) = **only** opens the **Socket Mode WebSocket** so Slack can push events to your laptop. Message *content* path uses `xoxb-`; event *delivery* path uses `xapp-`. Events API setups often skip `xapp-` (Slack POSTs your HTTPS URL instead).
- Link: M18, `slack_bot.py` (`SocketModeClient(app_token=..., web_client=WebClient(bot_token))`)

---

## 2026-09-05 — Dig: where OAuth tokens live (local JSON vs enterprise)

- **Q: Is writing the bot token to a local file “how Slack does auth”?**  
  A: **No.** Slack (and most OAuth apps) standardize the **handshake** (authorize → code → `oauth.v2.access` → token). **Storage is your app’s job.** Our `workspace/slack_installations.json` is a **teaching simplification**. Production: encrypted DB / secrets manager keyed by `team_id` (or org), never commit tokens, rotate/revoke, least privilege.
- **Q: Do agents/enterprise do the same?**  
  A: Same pattern family — **install once, store credential, reuse** — but storage and identity get stricter (Vault/KMS, SSO for *humans*, service accounts for *bots*, short-lived tokens where possible). Agent ↔ Slack is usually **bot/app credential**, not each end-user’s OAuth for every message.
- Link: M18, `slack_oauth.py` (`save_installation`)

---

## 2026-09-05 — Dig: Slack OAuth install vs day-to-day; Socket Mode vs Events API

- **Q: First install vs later runs — what is authorized when?**  
  A: **Install (OAuth v2)** = admin once grants scopes → you receive a long-lived **bot token** (`xoxb-`) per workspace, stored in `slack_installations.json`. **Later `run`** does **not** re-OAuth; it loads that token + `SLACK_APP_TOKEN` (`xapp-`) and opens Socket Mode. Re-install only when scopes change or token revoked.
- **Q: Socket Mode vs Events API?**  
  A: Same *event payload* shape; different *delivery*. **Events API** = Slack **HTTP POSTs** your public HTTPS URL (you are the server). **Socket Mode** = your process opens a **WebSocket outbound** to Slack and receives events (you are the client; no ngrok). Production SaaS often uses Events API + load-balanced HTTPS; local/dev and some enterprise setups prefer Socket Mode.
- Link: M18, `slack_oauth.py`, `slack_cli.py`, `slack_bot.py`

---

## 2026-09-05 — Dig: Slack multi-turn should not re-post full transcript

- **Q: Why did the second Slack reply include the first turn's "You: … / AI: …"?**  
  A: Checkpointer correctly keeps the **full session** for the model, but `format_agent_reply` was dumping **all** `result["messages"]` back into Slack. Thread UX already shows prior posts — reply should be **this turn only** (messages after the latest HumanMessage), and should not echo the user's HumanMessage.
- Fix: `messages_for_this_turn` + `format_agent_reply(..., this_turn_only=True)` in `slack_adapter.py`.
- Link: M18, `agent/slack_adapter.py`

---

## 2026-08-27 — M15: Lifecycle hooks

- Shipped: `agent/hooks.py` + `hook_demos.py`; Pre → permissions → body → Post; Stop on final AIMessage.
- Insight: Hooks are **pluggable lifecycle**; permissions are the **default policy table**; HITL is **durable human pause** — three different levers, one ToolNode.
- See Concept Q&A index (M15) below; Results: [M15](docs/milestones/M15-lifecycle-hooks.md).

---

## 2026-08-27 — Dig: why not full-async agent, or skip adapter with plain demo tools?

- **Q: Why not just go async like production? Or keep an MCP server but wire simple local `@tool` demos?**  
  A: **Two different shortcuts — both miss (or defer) the M14 lesson.** (1) **Full-async agent** *is* the cleaner production shape (adapter tools are coroutine-native; sync wrap is our bridge). We *can* do it; M14 deferred the rewrite of CLI / HITL / permission wrap / `graph.invoke` to keep the milestone about MCP merge, not “make the whole runtime async.” (2) **Plain local `@tool` + a decorative MCP server** teaches almost nothing about MCP: the model never goes through MCP schema discovery or the adapter. Demo `echo`/`add` live *on the MCP server*; the agent must speak the protocol (via adapter) or you are only demoing LangChain tools again (M1). Hand-written thin tools that call the MCP SDK yourself = rolling your own adapter.
- Link: M14, `tools/mcp_loader.py` (`wrap_mcp_tool_for_sync`)

---

## 2026-08-27 — M14: MCP client

- Shipped: `tools/mcp_loader.py` + in-repo `mcp_servers/echo_math.py`; opt-in `MCP_USE_DEMO` / `MCP_CONFIG` / `MCP_CONFIG_PATH`.
- Insight: MCP expands the **tool list** via adapter — same ReAct topology as skills/subagents layering, different mechanism (protocol tools vs prompt inject vs nested graph).
- Pitfall: adapter tools are async-only → sync wrap for ToolNode; content blocks flattened to strings.
- See Concept Q&A index (M14) below; full Results: [M14](docs/milestones/M14-mcp-client.md).

---

## 2026-08-30 — Dig: /help should not need Postgres

- **Q: Why did `./scripts/agent.sh "/help"` fail with Postgres connection refused?**  
  A: Bug: CLI allocated a HITL `thread_id` and opened the checkpointer **before** slash dispatch. `/help` / `/plugins` are meta list-only commands and must exit after printing the registry — no graph, no Postgres. Fixed by early `dispatch_slash_input` in `cli.main` before checkpointer setup. `/review` still needs a running agent stack (Postgres or `--checkpointer memory`).
- Link: `agent/cli.py`, M16

---

## 2026-08-28 — M16: Plugins & slash commands

- Shipped: `plugins.py`, `slash_commands.py`, `workspace/plugins/review`, CLI `/help` + `/review`.
- Insight: Plugin = **bundle** (slash + hooks); slash = **turn entry** template; hooks still **per tool**; graph unchanged.
- Results: [M16](docs/milestones/M16-plugins-slash-commands.md).

---

## 2026-08-30 — M17: Eval harness & cost/retry

- Shipped: `agent/retry.py`, `agent/usage.py`, `eval/runner.py`, `mcc-eval`, `./scripts/eval.sh`, CLI `--usage`.
- Insight: Eval sits **beside** the graph (YAML cases + scripted fake LLM); retry wraps **LLM invoke only**; usage reads `usage_metadata` with M7-style fallback estimate.
- Results: [M17](docs/milestones/M17-eval-harness-cost-retry.md).

---

## 2026-09-01 — M18: Slack OAuth → agent → open PR

- Shipped: `slack_oauth.py`, `slack_adapter.py`, `slack_bot.py`, `mcc-slack`, `open_pull_request` + `GH_TOKEN`.
- Insight: Slack = **interface adapter** (OAuth + Socket Mode); graph unchanged; GitHub = env token not OAuth.
- Results: [M18](docs/milestones/M18-chat-channel-open-pr.md).

---

## 2026-09-05 — M19: Pre-ship quality gate

- Shipped: `tools/ship.py` (`ship_check`, gate wrap, optional `git_push`), `./scripts/ship-check.sh`, ruff in dev deps.
- Insight: **ship_check** = local publish gate; **eval (M17)** = behavior regression. Enforce green before PR via tool wrap, not prompt hope. Fix-until-green is the ReAct loop + `SHIP_MAX_FIX_ITERS`.
- Results: [M19](docs/milestones/M19-pre-ship-quality-gate.md).

---

## Concept Q&A index (M0–M38 study guide)

Study this before starting any dig beyond the plugin lane (M23–M25 Done; M26 Done).

### M38 — Remote CI gate (GitHub Checks)

- **Q: How is M38 different from M19 ship_check?**  
  A: **M19** = local ruff + unit tests before opening a PR. **M38** = optional poll of **GitHub Checks/Actions** after a live PR. Laptop green does not imply Actions green.
- **Q: What states can remote wait return?**  
  A: `pending` (still running / no checks yet) → `green` | `red` | `timed_out`; plus `skipped` when `SHIP_REMOTE_CI=0`, dry-run, or missing token/PR.
- **Q: What happens on red or timeout?**  
  A: Tool returns structured failure JSON. If `SHIP_REMOTE_CI_HITL=1`, LangGraph `interrupt` asks the human to proceed anyway (override does **not** rewrite state to green).
- **Q: Why opt-in instead of always wait?**  
  A: Demos and dry-run PRs have no remote checks; always-wait would hang teaching loops. Production bots turn it on when shipping for real.
- Link: [M38](docs/milestones/M38-remote-ci-gate.md)

### M25 — Plugin install & trust

- **Q: What does install do vs trust?**  
  A: **Install** copies/clones into `workspace/plugins/<id>/` and writes a **disabled** trust row. **Trust** enables the pack and optionally grants `allow_mcp` / `allow_shell_hooks`.
- **Q: Can a disabled pack still affect the agent?**  
  A: **No** — `resolve_plugins` skips it (slash/skills/MCP/hooks from that pack stay out).
- **Q: Is allow_shell_hooks enough to run scripts?**  
  A: **No** — still need M24 `HOOK_SHELL_ENABLED=1` (defense in depth).
- **Q: What is still missing vs production?**  
  A: Signed packages, org policy UI, auto-updates, SBOM — labeled simplification (no marketplace).
- Link: [M25](docs/milestones/M25-plugin-install-trust.md)

### M24 — Plugin hooks & discovery

- **Q: How are shell hooks different from M15 ids?**  
  A: M15 handlers are **in-process Python** (`hook_demos`). M24 can also spawn a **script/command** with JSON stdin/stdout — portable pack policy without importing plugin Python into the agent.
- **Q: Why deny-by-default?**  
  A: Shell hooks are arbitrary code execution on the host. `HOOK_SHELL_ENABLED=0` skips them; when enabled, paths must be allowlisted or under `workspace/plugins/`.
- **Q: Does /pick change the graph?**  
  A: **No.** It is CLI discovery that expands to a normal HumanMessage (same as `/review`).
- **Q: Wrap order still?**  
  A: Unchanged: **Pre → permissions/HITL → body → Post** (shell Pre is just another Pre handler).
- Link: [M24](docs/milestones/M24-plugin-hooks-discovery.md)

### M23 — Plugin pack expansion

- **Q: What did M16 plugins lack?**  
  A: Only **slash + hook ids**. Industry packs also ship **skills**, **MCP**, and **subagent** defs as one product surface.
- **Q: Does a plugin add LangGraph nodes?**  
  A: **No.** It merges into existing planes: slash (CLI), hooks, skills catalog/`load_skill`, MCP connections, `run_subagent` defs.
- **Q: How do collisions fail?**  
  A: Duplicate slash / skill name / MCP server name / subagent name → **ValueError** (fail closed), not silent override.
- **Q: Why does fake_docs appear without MCP_USE_FAKE_DOCS?**  
  A: Seeded **`docs-mcp`** pack declares `mcp.fake_docs.preset`. Pack contribution ≠ env flag. Disable with `PLUGINS_ENABLED=0` or remove the pack.
- **Q: What is still deferred?**  
  A: **M24** shell hook runners / richer discovery; **M25** install CLI + trust allowlist.
- Link: [M23](docs/milestones/M23-plugin-pack-expansion.md)

### M37 — Prompt caching & budgeted compaction

- **Q: Soft budget vs compact threshold?**  
  A: Threshold (M7) is the legacy trigger. Soft budget (`CONTEXT_TOKEN_BUDGET`) is an optional cost target. When both > 0, fire at **`min(threshold, budget)`** so budget can tighten but not raise. Either alone works; both ≤ 0 disables.
- **Q: What does prompt caching actually cache?**  
  A: A **stable prefix** (system / tools / long docs) hashed by the provider. We mark the last leading `SystemMessage` + pass Anthropic invoke `cache_control`. Volatile chat turns should sit *after* the breakpoint.
- **Q: Why not one `enable_cache=True` for all providers?**  
  A: Wire formats differ (Anthropic `cache_control` vs OpenAI-era APIs vs Ollama). Teaching value is the asymmetry — thin helpers, labeled no-ops elsewhere.
- **Q: Cache hit vs usage estimate?**  
  A: `--usage` prefers provider `usage_metadata` (`input_token_details.cache_read` / `cache_creation`). First short call may show `cache: n/a`; hits need a warm prefix.
- Link: [M37](docs/milestones/M37-prompt-cache-budget.md)

### M36 — RAG / agent eval quality

- **Q: Smoke eval vs quality eval?**  
  A: **M17** checks scripted agent paths didn’t crash / expected strings. **M36** asks whether the **right chunk** ranked (hit@k) and whether answers are **grounded** in evidence.
- **Q: How do we know retrieval “helped”?**  
  A: Fixed world (golden corpus + distractors) + labeled answers (qrels cites). Success = **hit@k=1** for that query (correct cite in top-k). Faithfulness is a second gate: markers must live in evidence text. Together: “right doc retrieved” + “evidence actually contains the claim tokens.”
- **Q: What is a golden corpus / qrels?**  
  A: Golden corpus = tiny fixture docs we control (`exact_token.md`, `semantic_pref.md`, `distractor.md`). Qrels = per-query expected cites (`docs/exact_token.md#0`) + optional `required_spans`. Without labels you only get “something returned.”
- **Q: What is hit@k?**  
  A: 1 if any golden cite (`source_path#chunk_index`) appears in the top-k ranked results; else 0. Average across queries for a suite score. MRR is softer: `1/rank` of first relevant hit.
- **Q: Deterministic faithfulness vs soft judge?**  
  A: Deterministic = required spans must appear as substrings in joined evidence (CI-stable). Soft = optional `GradeResult` LLM judge (flaky; skip without key). Teaching simplification: substring ≠ full NLI.
- Link: [M36](docs/milestones/M36-rag-agent-eval-quality.md)

### M35 — Multi-agent handoff (swarm-lite)

- **Q: Is handoff just another form of subagent?**  
  A: **No.** Same “multi-role” family, different **control contract**. M12 = nested invoke (parent keeps control). M35 = `active_agent` **transfers** until handoff back / finish.
- **Q: How do we stop A↔B ping-pong?**  
  A: Hard **bounce cap** on `handoff_count`; disallowed edges (star: specialists → supervisor only).
- **Q: How is context isolated?**  
  A: Specialists see turn-local messages + shared **scratchpad**, not peer `ToolMessage` soup; supervisor strips raw tool bodies.
- Link: [M35](docs/milestones/M35-multi-agent-handoff.md)

### M34 — Observability traces

- **Q: Stream vs usage vs traces vs checkpoints?**  
  A: **Stream (M6)** = live UX. **`--usage` (M17)** = local token footer. **Traces (M34)** = durable LLM/tool span tree (LangSmith or JSONL). **Checkpoints (M31)** = session time-travel, not span debug.
- **Q: Did tracing change the graph?**  
  A: **No.** Enrich `RunnableConfig` metadata/tags + optional callbacks. Same `call_model` ⇄ `PolicyToolNode`.
- **Q: How does LangSmith turn on?**  
  A: Env opt-in: `LANGCHAIN_TRACING_V2=true` + `LANGSMITH_API_KEY` (+ project). Framework emits runs when config is passed; we stamp `thread_id`/model metadata.
- **Q: What is local JSONL for?**  
  A: Offline teaching without SaaS — `--trace-local` / `MCC_TRACE_JSONL` writes redacted llm/tool events.
- Link: [M34](docs/milestones/M34-observability-traces.md)

### M33 — Structured outputs & forced tool choice

- **Q: Is structured output “don’t use the model / only tools”?**  
  A: **No.** Still model-driven. Schema constrains **reply shape**; `tool_choice` constrains **which tool_call**.
- **Q: Structured output vs function/tool call?**  
  A: Structured = validated **data object** (route/grade). Tool call = execute a tool. Some providers implement schema via internal tools — plumbing only.
- **Q: Who enforces `RouteDecision` — LLM or LangChain?**  
  A: Provider may constrain generation; LangChain orchestrates extract; **Pydantic** is the local gate (`model_validate`). Retry optional.
- **Q: Is `BaseModel` from LangChain?**  
  A: **No** — from **Pydantic**. LangChain optionally consumes your class.
- Link: [M33](docs/milestones/M33-structured-output-tool-choice.md)

### M32 — Parallel tools & fan-out

- **Q: What does tools fan-out mean?**  
  A: One `AIMessage` with N `tool_calls` → runtime runs those tools **concurrently**, then gathers `ToolMessage`s. Scheduling inside the `tools` node — not a new graph edge.
- **Q: Was ToolNode serial before M32?**  
  A: **No.** LangGraph already used gather / thread pool. M32 adds **policy**: serial A/B, ask-batch serial, concurrency cap, explicit error isolation.
- **Q: Why serialize when any tool is ask?**  
  A: Concurrent `interrupt()` races HITL resume. Safer: that tools step runs one call at a time.
- **Q: Does fan-out bypass permissions/hooks?**  
  A: **No.** Wrap onion still runs **per call** (Pre → permissions/HITL → body → content policy → Post).
- Link: [M32](docs/milestones/M32-parallel-tools-fanout.md)

### M31 — Time-travel & branch sessions

- **Q: Resume vs time-travel?**  
  A: M5 resume always continues the **tip** of a `thread_id`. Time-travel picks a past **`checkpoint_id`** and **forks** a new future.
- **Q: Fork vs overwrite?**  
  A: M31 forks onto a **new `thread_id`** (copy snapshot values). Source tip stays. Silent tip rewrite is the anti-pattern.
- **Q: Why clear `checkpoint_id` after fork?**  
  A: Config with a pinned id makes `get_state` return that frozen snapshot even after newer turns on the thread.
- **Q: Store (M30) vs rewind?**  
  A: Store = cross-thread **KV**. Rewind = **chat transcript** checkpoints. Different jobs.
- Link: [M31](docs/milestones/M31-time-travel-branch.md)

### M30 — LangGraph Store

- **Q: What crosses sessions / threads?**  
  A: **Checkpointer** = one thread’s chat only. **Store** = exact KV in a project namespace (any thread). **Neo4j / pgvector / AGENT.md** = existing semantic/fuzzy/always-on long-term — kept beside Store.
- **Q: Who controls what gets stored?**  
  A: **Dev** = which memory systems + namespace/schema. **Policy** = may the write tool run. **LLM** = when to `store_put`/`store_get` (tool choice). **User** = prompts, HITL, edit `AGENT.md`. M30 default is not “auto-save the whole chat.”
- **Q: DB layout for cross-session?**  
  A: Store → SQL `store(prefix, key, value jsonb)`; notes/chunks → `memory_notes` / `memory_chunks` + vectors; facts → Neo4j `:Fact`; chat → checkpointer `thread_id` tables (not shared across threads).
- **Q: Tell the agent to remember → cross-session?**  
  A: Yes if it calls `store_put` / `remember_fact` / `remember_note` (or you edit `AGENT.md`). Chat-only text stays in that thread’s checkpointer.
- Link: [M30](docs/milestones/M30-langgraph-store.md)

### M29 — MCP HTTP & sticky session

- **Q: So we become a real MCP server?**  
  A: **Agent stays the client.** M29 = HTTP transport + sticky session on the **client** path, plus a **tiny in-repo demo HTTP server** for teaching. Not “productize ourselves as MCP SaaS.”
- **Q: Remotely reachable by others?**  
  A: **Protocol yes** (URL vs local spawn). M29 demo is **localhost** by default; public bind + OAuth = later / out of scope.
- **Q: Sticky vs cold `get_tools`?**  
  A: Cold = new session per tool call (counter resets). Sticky = one `client.session(...)` reused (counter accumulates). Stdio demos stay on cold path for contrast.
- **Q: Why a dedicated sticky loop/thread?**  
  A: Graph build is often sync; MCP `ClientSession` is loop-affine. Bridging tool calls onto a sticky loop keeps session alive across sync and async CLI paths.
- **Q: Teardown traceback / cancel scope error?**  
  A: Open and close the HTTP session in the **same** asyncio Task (owner task + stop event). Splitting open/close across `run_until_complete` calls breaks anyio.
- Link: [M29](docs/milestones/M29-mcp-http-session.md)

### M28 — Graph-neighbor expand

- **Q: Tool only — no new agent call layer?**  
  A: **Yes.** No new LangGraph node / forced LLM / subagent. Same `call_model` ↔ tools; expand is an optional tool step. Extra model turns = normal ReAct after tool results, not a pipeline “layer.”
- **Q: Why not auto-expand inside `search_chunks`?**  
  A: Hides the island vs sequence lesson and bloats every hit. Agent (and you) should choose when neighbors are worth the tokens.
- **Q: Join / cite key?**  
  A: Same as M20/M27: `(doc_id, chunk_index)` / `{doc_id}:{chunk_index}` → `source_path#index`. Not pgvector UUID.
- **Q: NEXT vs CONTAINS?**  
  A: Expand walks **NEXT** (structure). CONTAINS/`search_chunks_keyword` stays emergency keyword only.
- Link: [M28](docs/milestones/M28-graph-neighbor-expand.md)

### M27 — Hybrid retrieval

- **Q: Why not one “search everything” tool?**  
  A: Solo ES / solo vector teach different failure modes. Hybrid is a **staged** choice the agent (and you) should see.
- **Q: What is the join key?**  
  A: **`(doc_id, chunk_index)`**. ES `_id` is `{doc_id}:{chunk_index}`; pgvector PK is a UUID — do not join on UUID.
- **Q: Empty ES — fall back to `search_chunks`?**  
  A: **No (default).** Empty keyword stage → empty hybrid, so the contract stays honest. Call `search_chunks` explicitly if you want paraphrase-only.
- **Q: RRF or cross-encoder?**  
  A: Deferred. M27 is filter-then-embed only.
- Link: [M27](docs/milestones/M27-hybrid-retrieval.md)

### M26 — MCP content policy & safety

- **Q: How is M26 different from M9 permissions?**  
  A: M9 gates **tool names** (auto/ask/deny). M26 inspects **returned text** (title / first line / H1 markers). A tool can be auto-allowed and still return `CONTENT_POLICY_DENIED`.
- **Q: How is M26 different from M15 hooks?**  
  A: Hooks see **name/args** (and can audit after). They do not, by default, parse document bodies for DLP markers. Content policy is a dedicated result screen.
- **Q: Why both server deny and client wrap?**  
  A: **Server** = source of truth; hostile/forgetful MCP cannot be fixed by client alone. **Client wrap** = defense-in-depth + same rules for builtin `read_file`. Teaching both clarifies the trust boundary.
- **Q: Without M26, what degrades?**  
  A: Any permitted `read_doc` / `read_file` can dump confidential text into the transcript → model context forever (and logs).
- **Q: Is first-line `no-ai` production-ready?**  
  A: **Simplification.** Real Drive/Docs need labels, ACLs, and store-side enforcement — not only a markdown convention.
- Link: [M26](docs/milestones/M26-mcp-content-policy.md)

### M22 — Async agent runtime

- **Q: Why did MCP need `asyncio.run` before?**  
  A: Adapter tools were coroutine-first; sync ToolNode needed a `func`. M14 added `asyncio.run(ainvoke)`. That is fine only when **no event loop is running**.
- **Q: What was the deeper bug?**  
  A: Permission/hook wraps rebuilt tools with **only `func`**, dropping `coroutine`. Even `graph.ainvoke` then called sync `invoke` → nested `asyncio.run`.
- **Q: What does M22 change?**  
  A: Wraps expose **`func` + `coroutine`** (`await tool.ainvoke`). CLI defaults to **`ainvoke`/`astream`**. MCP sync shim remains for `--sync` / tests, not the hot path.
- **Q: Why is `call_model` still sync?**  
  A: LangGraph sync `invoke` cannot run async-only nodes; keeping sync preserves the unit suite. Async win is primarily the **tool plane**.
- **Q: Why did default chat/REPL fail on Postgres after M22?**  
  A: Sync `PostgresSaver` has no `aget_tuple`. Default `ainvoke` needs **`AsyncPostgresSaver`** (`open_async_checkpointer`). `--sync` still uses `open_checkpointer`. Empty error text = `NotImplementedError()` with blank `str`.
- Link: [M22](docs/milestones/M22-async-agent-runtime.md), `open_async_checkpointer`

### M21 — Elasticsearch full-text

- **Q: Does `search_keyword` reimplement BM25?**  
  A: **No.** ES owns the inverted index + BM25. We index chunk docs and call `multi_match`; the engine scores.
- **Q: Why a separate tool instead of folding into `search_chunks`?**  
  A: Different retrieval family. One tool that “sometimes semantic sometimes keyword” hides the lesson. Agent (and you) should **choose** ES vs vectors on purpose.
- **Q: When ES vs pgvector vs Neo4j?**  
  A: **ES** = exact tokens / must-contain. **pgvector** = paraphrase / fuzzy intent. **Neo4j** = relations + M8 Facts (CONTAINS remains a weak emergency path only).
- **Q: Is hybrid in M21?**  
  A: **No** — deferred dig (ES filter + vector re-rank). First learn each store alone.
- Link: [M21](docs/milestones/M21-elasticsearch-fulltext.md)

### M20 — Doc ingestion & memory pipeline

- **Q: Does Neo4j “do chunking”?**  
  A: **No.** Chunking/cleaning is an **ingestion pipeline**. Neo4j (and pgvector) only **store** Document/Chunk rows the pipeline writes. Confusing the two hides why RAG quality lives in ingest, not in Cypher.
- **Q: Why both pgvector chunks and Neo4j Document/Chunk?**  
  A: Same chunks, different questions. **pgvector** = “find text *like* this” (embeddings). **Neo4j** = structure/provenance (`HAS_CHUNK`, `NEXT`) and cheap keyword CONTAINS. M8 `Fact` stays for crisp beliefs — not file body storage.
- **Q: ingest_docs vs remember_note / remember_fact?**  
  A: **ingest_docs** = batch files → many chunks + metadata. **remember_note** = one ad-hoc blurb. **remember_fact** = one durable preference/truth node. Wrong tool → either un-citeable blobs or graph spam.
- **Q: Without metadata, what degrades?**  
  A: The model cannot cite `docs/foo.md#2`; re-ingest cannot replace by path; debugging “why this hit?” becomes opaque.
- **Q: Why sync tool call, not a job queue?**  
  A: Teaching simplification — one ReAct turn runs the pipeline. Production multi-tenant ingest still needs workers, retries, ACL, and evals (labeled in Results).
- Link: [M20](docs/milestones/M20-doc-ingestion-memory-pipeline.md)

### M19 — Pre-ship quality gate

- **Q: ship_check vs M17 eval?**  
  A: **Eval** = scripted agent-behavior cases (often fake LLM). **ship_check** = **this repo’s** ruff + unit tests before you publish a change.
- **Q: Who runs the fix loop?**  
  A: The **ReAct agent** (edit tools → ship_check again). The gate only records pass/fail and **blocks** `open_pull_request` until green; `SHIP_MAX_FIX_ITERS` stops infinite consecutive fails.
- **Q: Why wrap open_pull_request?**  
  A: Prompt-only “please run tests first” is unreliable. A wrap returns `SHIP_GATE: …` so the model cannot dry-run/live PR without a green check when `SHIP_REQUIRE_GREEN=1`.
- **Q: SHIP_MODE=pr vs push?**  
  A: Default **pr** — open PR only. **push** also exposes `git_push` (ask + green, never `--force`).
- **Q: Why checks use repo root not workspace/?**  
  A: Agent FS jail is for demos; shipping quality is about **mini-claude-code** itself (`backend/` tests).
- Link: [M19](docs/milestones/M19-pre-ship-quality-gate.md)

### M18 — Slack OAuth channel + open PR

- **Q: Why Slack OAuth instead of pasting a bot token?**  
  A: Production Slack apps use **OAuth v2 install** — each workspace gets its own bot token stored after admin approval. Pasting `SLACK_BOT_TOKEN` in `.env` is still supported as a **shortcut** for local dev.
- **Q: First install vs later `run` — call chain?**  
  A: **Install once:** authorize URL → Allow → local callback `code` → `oauth.v2.access` → save `xoxb-` by `team_id`. **Later run:** load stored `xoxb-` + `SLACK_APP_TOKEN`; **no browser OAuth**. Re-install only when scopes change / revoke / new workspace.
- **Q: Why both `xoxb-` and `xapp-`?**  
  A: **`xoxb-`** = act as bot (Web API: post message, reactions). **`xapp-`** = open Socket Mode WebSocket only (`connections:write`). Delivery vs action — two keys.
- **Q: Is local JSON token storage “how Slack / enterprise does it”?**  
  A: **No.** OAuth *handshake* is standard; *storage* is our job. `slack_installations.json` = teaching simplification. Production: encrypted Installation Store / Vault / KMS keyed by org; SSO is for *humans* logging into consoles, not each Slack message.
- **Q: Socket Mode vs Events API?**  
  A: Same event *shape*; different *delivery*. Events API = Slack HTTPS POSTs your public URL (you are server). Socket Mode = you open outbound WebSocket (you are client; no ngrok). Socket carries **inbound events**; replies still use HTTPS Web API with `xoxb-`.
- **Q: Does `slack.sh run` keep listening? Production too?**  
  A: **Yes** — long-lived process (`connect` + wait). Enterprise also needs always-on receivers, but usually as a service + **ack fast / queue agent work** / multi-replica — not one laptop script running the LLM inline.
- **Q: Why Socket Mode?**  
  A: Local dev without a public HTTPS URL (no ngrok). App-level `SLACK_APP_TOKEN` + bot token receive events over a WebSocket.
- **Q: Slack OAuth vs GitHub OAuth?**  
  A: **Different layers.** Slack OAuth = who may run the bot in a workspace. **GitHub = `GH_TOKEN`** in M18 (server-side PAT) — simpler for a learning repo; per-user PR attribution is a later dig.
- **Q: Channel vs graph?**  
  A: Adapter maps `slack:{team}:{channel}:{thread}` → checkpointer `thread_id`, then same `build_agent_graph`. No new LangGraph nodes.
- **Q: HITL in Slack?**  
  A: Default **`CHANNEL_PLAN_MODE=1`** (read-only). Non-plan: reply `approve` / `deny` in thread to resume interrupt.
- **Q: Does `open_pull_request` push?**  
  A: **No.** Creates PR via `gh`/REST when `PR_DRY_RUN=0`; head branch must already exist on remote.
- **Q: Why did multi-turn Slack replies repeat old turns?**  
  A: Checkpointer returns the **full** transcript; Slack reply must format **only this turn** (after the latest HumanMessage) and skip echoing the user's message. Fixed in `format_agent_reply` / `messages_for_this_turn`.
- Link: [M18](docs/milestones/M18-chat-channel-open-pr.md)

### M17 — Eval harness & cost/retry

- **Q: Eval vs pytest?**  
  A: **pytest** pins functions and branches with mocks. **Eval** runs the **whole agent graph** on YAML scenarios (prompt + fake-LLM script + transcript assertions) — closer to “did the agent behave sensibly on this turn sequence?”
- **Q: Why eval outside LangGraph?**  
  A: Same Option B lesson as hooks/plugins — regression harness is **orchestration around** `build_agent_graph`, not a new cognition node.
- **Q: Retry vs HITL?**  
  A: **Retry** = automatic backoff on transient LLM/API errors at `bound.invoke`. **HITL** = deliberate human pause on risky **tools**. Different failure modes; retry does not re-ask the user.
- **Q: Usage vs compaction `estimate_tokens`?**  
  A: **Compaction (M7)** estimates proactively to **prevent** context overflow. **Usage (M17)** measures **after** LLM calls — prefers `usage_metadata`, falls back to chars/4 when providers omit it.
- **Q: What does `--usage` show?**  
  A: Per-run footer: `llm_calls`, input/output/total tokens, plus count of calls that needed fallback estimate.
- Link: [M17](docs/milestones/M17-eval-harness-cost-retry.md)

### M16 — Plugins & slash commands

- **Q: What is a plugin here?**  
  A: A **declarative pack** (`workspace/plugins/<id>/plugin.yaml`) that can register **slash commands** (prompt templates) and optionally **append hook handler ids** — not a new graph node or pip package.
- **Q: Plugin vs slash vs hook vs skill?**  
  A: **Slash** = user types `/review` → CLI expands template once at turn entry. **Hook** = Pre/Post around every tool call. **Skill** = playbook in context via `load_skill`. **Plugin** = container that can ship slash + hooks together.
- **Q: Why `/help` not interactive `/plugins` menu?**  
  A: **方案 A** — list-only discovery (like Claude Code’s catalog, without TUI picker). User still types `/review` manually; interactive menu = later dig.
- **Q: Where does slash run?**  
  A: **CLI/REPL** (`dispatch_slash_input`) before `graph.invoke` — not inside LangGraph.
- **Q: Hook merge order?**  
  A: Base `hooks.yaml` / demo / env path first, then **append** plugin hook ids; dedupe within each list.
- **Q: How do industry plugins compare?**  
  A: Same **pack + merge** idea; industry packs usually also bundle skills, MCP, subagents, shell hooks, install/trust. M16 = slash + hook id only. Parked: **[M23](docs/ROADMAP.md)** (pack expansion), **[M24](docs/ROADMAP.md)** (shell hooks + picker), **[M25](docs/ROADMAP.md)** (install/trust).
- Link: [M16](docs/milestones/M16-plugins-slash-commands.md)

### M15 — Lifecycle hooks

- **Q: Hooks vs permissions vs HITL?**  
  A: **Permissions** = fixed auto/ask/deny table (M9). **HITL** = ask pauses with `interrupt` + resume (M10). **Hooks** = pluggable Pre/Post/Stop callbacks (audit, redact, custom deny) without new graph nodes.
- **Q: Why outer wrap?**  
  A: `apply_permissions` first (inner), then `apply_hooks` (outer) so runtime order is Pre → permissions/HITL → body → Post.
- **Q: What is Stop here?**  
  A: Best-effort when `call_model` returns an AIMessage **without** tool_calls — not OS process exit. Fires again each REPL turn that ends that way.
- **Q: Empty config?**  
  A: No `HOOKS_CONFIG_PATH`, no `workspace/hooks.yaml`, `HOOKS_USE_DEMO=0` → empty registry → behavior unchanged from M14.
- Link: [M15](docs/milestones/M15-lifecycle-hooks.md)

### M14 — MCP client

- **Q: MCP vs skills vs sub-agents?**  
  A: **Skills** = playbook text injected into *this* agent's context. **Sub-agent** = nested child graph (`run_subagent`). **MCP** = *callable tools* discovered from an external server via protocol + adapter — still one ToolNode hop, not a nested agent.
- **Q: Why an adapter?**  
  A: MCP wire format ≠ LangChain `BaseTool`. `langchain-mcp-adapters` (`MultiServerMCPClient.get_tools`) converts schemas so `bind_tools` / `ToolNode` work unchanged. Topology stays Option B.
- **Q: Do we run a local MCP server?**  
  A: Yes for teaching — in-repo stdio `echo_math` (`echo` / `add`). Agent is the **client**. Opt-in: `MCP_USE_DEMO=1` or `MCP_CONFIG` / `MCP_CONFIG_PATH`. Empty config = no MCP.
- **Q: Why a sync wrap around MCP tools?**  
  A: Adapter tools are often **coroutine-only**. Our sync `graph.invoke` / ToolNode / permission wrap call `invoke`. M14 wraps with `asyncio.run(ainvoke)` (**simplification**; full-async agent is the real fix).
- **Q: Why not full-async now, or plain local demo tools instead of the adapter?**  
  A: Full-async is the better long-term shape — deferred so M14 stays about MCP merge, not rewriting CLI/HITL. Parked as **[M22](docs/ROADMAP.md)** (Tier 4 optional). Plain `@tool` demos (with an unused MCP server) skip the protocol/adapter lesson; the demo tools must be *served over MCP* and discovered via the client.
- **Q: Stateless sessions?**  
  A: Default `get_tools()` path often starts a **new stdio session per tool call**. Fine for echo/add; use explicit `client.session(...)` when the server must keep state (later dig).
- Link: [M14](docs/milestones/M14-mcp-client.md)

### M13 — Skills (progressive disclosure)

- **Q: Skill vs sub-agent?**  
  A: Skill = load playbook into **this** agent’s context (`load_skill`). Sub-agent = **child graph** with fresh messages (`run_subagent`).
- **Q: What is progressive disclosure?**  
  A: L0 catalog (name+description) every turn; L1 full body only after `load_skill`. Saves context vs dumping all playbooks into the system prompt.
- Link: [M13](docs/milestones/M13-skills-progressive-disclosure.md)

### M12 — Sub-agents

- **Q: What is a sub-agent here?**  
  A: A **child ReAct graph** invoked from the parent tool `run_subagent`. Fresh messages + YAML tool allowlist; returns a text summary. Same model as parent.
- **Q: Does the child see the parent chat?**  
  A: **No** — only the `task` string (+ child system brief). That is the isolation lesson.
- **Q: Why a tool, not new parent nodes?**  
  A: Option B — keep parent topology `call_model` ↔ `tools`; grow capability via tools.
- Link: [M12](docs/milestones/M12-sub-agents.md)

### M11 — Docker sandbox

- **Q: Is cwd=workspace a sandbox?**  
  A: **No** (M4). M11 runs `run_shell` in `docker run --rm` with only the workspace mounted at `/workspace`.
- **Q: Do permissions go away?**  
  A: No — M9/M10 still gate; sandbox is *where* an allowed command runs.
- **Q: Why not put `git_*` in Docker too?**  
  A: Structured git is intentional host VCS on the project tree; blast radius is shell/arbitrary commands.
- **Q: Default network none?**  
  A: Teaching default blocks egress; real agents often need allowlisted network later.
- Link: [M11](docs/milestones/M11-docker-sandbox.md)

### M10 — Human-in-the-loop (`interrupt`)

- **Q: What changed vs M9 ask?**  
  A: Policy table unchanged. Ask no longer relies on production `ask_callback` / stdin inside the wrap. Ask calls LangGraph `interrupt(payload)`; CLI uses `Command(resume=True/False)` after y/n. Needs a checkpointer + `thread_id` (CLI auto-allocates if missing when not in Plan Mode).
- **Q: Why not `interrupt_before=["tools"]`?**  
  A: That pauses *every* tool entry (including reads). Dynamic `interrupt()` inside the wrap pauses only when policy says `ask`.
- **Q: Does topology change?**  
  A: No — still `call_model` ↔ `tools`. HITL is in the policy wrap + CLI resume loop (`agent/hitl.py`).
- **Q: Streaming + HITL?**  
  A: **Simplification:** HITL path uses `invoke`; Plan Mode can still token-stream. Combining stream + Command is a later polish.
- Link: [M10](docs/milestones/M10-human-in-the-loop-interrupt.md)

### M9 — Permissions & Plan Mode

- **Q: Why a policy plane instead of new Approve graph nodes?**  
  A: Keep ReAct as cognition (`call_model` ↔ `tools`). Permissions decide *before* the tool body; deny returns a synthetic message so the loop continues. Topology stays teachable; M10/HITL and channels share one decision function.
- **Q: auto / ask / deny — defaults?**  
  A: Read-safe (`read_file`, `glob_files`, `grep_files`, git read, `recall_*`) → `auto`. Mutators (`write_file`, `edit_file`, `run_shell`, `git_commit`, `remember_*`) → `ask`. Plan Mode forces mutators → `deny`.
- **Q: What is Plan Mode?**  
  A: `--plan` / `AGENT_PLAN_MODE` — read-only session via policy override, not prompt hope. Model may still *attempt* writes; execution is denied.
- **Q: Why is ask only CLI stdin in M9?**  
  A: Teaches the **decision** without durable pause. Non-TTY → deny. M10 replaces ask with LangGraph `interrupt` + checkpointer resume (survives process death / remote adapters).
- **Q: Why skip path ACL / “always allow this command”?**  
  A: Those are **product rules on top of** the policy plane (more tables/UX/persistence). They blur into M10 session grants and M11 sandbox; shipping them now hides the Option B lesson. See dated dig entry below.
- Link: [M9](docs/milestones/M9-permissions-plan-mode.md)

### M0 — Environment & provider skeleton

- **Q: Provider vs model vs protocol? Why OpenRouter + OpenAI + Anthropic + Ollama?**  
  A: Config picks a **provider** *and* a **model id**. OpenRouter is still OpenAI-compatible wire format (`ChatOpenAI` + gateway `base_url`), not a fourth protocol. Anthropic is the odd Messages API out. Naming OpenRouter as its own provider documents the gateway pattern.
- **Q: Why start Neo4j / pgvector before we use them?**  
  A: **Provision vs use** — ops ready early so later milestones don’t reinvent Compose mid-learning.
- **Q: Can every architecture option support sub-agents later?**  
  A: Yes in principle; Option B (small ReAct core + policy plane) makes subgraphs/HITL attach cleanly without a god-object graph. We chose Option B to learn more of the LangGraph/LangChain surface.
- **Q: Do Results / graphs / LEARNING_LOG belong in the plan?**  
  A: Yes — every milestone Plan has Results + Testing; graphs freeze after approval; Learning Log records insights + Concept Q&A.
- Link: [M0](docs/milestones/M0-environment.md)

### M1 — Tool-calling parity

- **Q: With multiple providers/models, how do we keep tool-call and chat formats compatible?**  
  A: One LangChain tool + messages (`HumanMessage` / `AIMessage` / `ToolMessage`); **adapters** map wire formats. We do **not** maintain four schemas in agent code.
- **Q: Is `parity.py` the compatibility layer? What’s the call chain?**  
  A: No — `parity.py` is a **probe**. Real path: agent messages → `bind_tools` / chat model → provider adapter → wire API. M2 consumes the normalized message layer; it does not replace it.
- **Q: Why mandatory unit + integration tests every milestone?**  
  A: Tests are part of the learning archive — Plan lists cases; Done requires them; later you can re-learn behavior by reading tests.
- Link: [M1](docs/milestones/M1-tool-calling-parity.md), [notes](docs/notes/tool-calling-parity.md)

### M2 — Minimal ReAct StateGraph

- **Q: Is the graph “just END or tools”? Does LangGraph hide the complexity?**  
  A: Topology is intentionally tiny (`call_model` ↔ `tools`). Value is **runtime hooks** (checkpointer / interrupt / stream / subgraph), not “tools magic.” Capability grows via the **tool list**, not new nodes.
- **Q: Is there a hidden while-loop? Where does the `add` tool live?**  
  A: No hand-rolled loop — conditional edges: answer → END, else → tools → back to model. Demo `add` is registered with the tools list at graph build.
- **Q: Do we need FastAPI / a running server to chat? Is uv / venv required?**  
  A: CLI via `./scripts/agent.sh` → `uv run` into the project env — no FastAPI for continuous chat. Durable sessions later = `thread_id` + checkpointer (M5), not “start an HTTP server.”
- **Q: One-shot CLI vs continuous session like Claude Code?**  
  A: Same core: multi-turn = reload state by `thread_id`. HTTP/IDE are **adapters** around the graph, not a rewrite.
- **Q: MCP in this project?**  
  A: Planned later (roadmap Tier-3); not required for M2 ReAct.
- Link: [M2](docs/milestones/M2-react-stategraph.md)

### M3 — Filesystem tools

- **Q: Will we add read/write/edit? What is glob?**  
  A: Yes — path-jailed FS tools. `glob` = find files by pattern (name/path), complementary to content search (`grep`).
- **Q: Where is `resolve_in_workspace` called?**  
  A: Every FS tool path goes through the jail helper before touching disk (read/write/edit/glob/grep) — prevents escaping the workspace root.
- **Q: How do I run unit tests without fighting the env?**  
  A: `./scripts/test.sh …` (uv-managed). Don’t `python tests/...` from a random interpreter.
- **Q: What are `cli.py`, `factory.py`, `parity.py`, `config.py`, `smoke.py` for?**  
  A: `config` = settings; `factory` = build `BaseChatModel` (e.g. `ChatOpenAI` subclass); `cli` = agent entry; `smoke` / `parity` = probes (`mcc-smoke`, `mcc-tools-parity` via pyproject scripts); not “the agent loop.”
- Link: [M3](docs/milestones/M3-filesystem-tools.md)

### M4 — Shell & git

- **Q: What is VCS? Why shell *and* git tools? subprocess?**  
  A: VCS = version control (git here). Structured `git_*` for clear schemas; `run_shell` for the long tail — both still host `subprocess`. Alternatives (libgit2, etc.) skip the real CLI surface coding agents use.
- **Q: Are git tools `list[BaseTool]`? Why no `git push`?**  
  A: Yes — schemas the LLM can call. No push by design until a permissioned ship path (later M18/M19).
- **Q: cwd a sandbox?**  
  A: **No.** `cwd=workspace` ≠ isolation; denylist is a teaching brake; real sandbox is M11.
- Link: [M4](docs/milestones/M4-shell-git-tools.md)

### M5 — Postgres checkpointer & sessions

- **Q: Continuous chat without FastAPI — is “read DB each turn” enough?**  
  A: Yes — durable `thread_id` + checkpointer restores `messages`; CLI can stay process-per-turn.
- **Q: MemorySaver vs Postgres?**  
  A: Same graph API; MemorySaver dies with the process; Postgres survives restarts.
- **Q: Where is Postgres? I only see one Docker thing named mini-claude-code?**  
  A: `docker-compose.yml`. Compose **project** name (= repo folder) ≠ one app container. Services: `mcc-postgres`, `mcc-neo4j`. `docker compose up -d` starts both DBs.
- **Q: Why `db-inspect`?**  
  A: See LangGraph checkpoint tables / `thread_id`s (and later Neo4j) so resume isn’t a black box.
- Link: [M5](docs/milestones/M5-postgres-checkpointer.md)

### M6 — Streaming CLI

- **Q: Why streaming? What if we skip it?**  
  A: Same final state as `invoke` — streaming changes **when** you see tokens/events (UX, debug, later HITL/channels), not model intelligence.
- **Q: Is `stream_cli` / `stream_render` a second entrypoint?**  
  A: No — entry remains `cli.py` / `mcc-agent`. Helper only **renders** `graph.stream` events (renamed to `stream_render` to avoid confusion).
- **Q: `messages` vs `updates` vs `values`? Why subscribe to all three?**  
  A: Tokens; per-node milestones (tool runs show up here); full state snapshots. Pure chat barely needs `updates`; coding agents do — without `updates`, the tool phase looks hung after tokens finish.
- **Q: Does `values` keep all 10 turns?**  
  A: Each `values` event is a **full state snapshot** at that point (growing history under checkpointer), not “only the latest user line.”
- **Q: Why pass `config` into `model.invoke`?**  
  A: Required for LangGraph `stream_mode="messages"` token callbacks.
- Link: [M6](docs/milestones/M6-streaming-cli.md)

### M7 — Context compaction

- **Q: Compact = compress the chat when too long?**  
  A: Yes — when estimated size (`chars/4`) > `CONTEXT_COMPACT_THRESHOLD`, summarize older turns and keep `CONTEXT_KEEP_RECENT` verbatim. Gate in `maybe_compact_messages`; wired from `call_model`.
- **Q: Where is the threshold in code / config?**  
  A: Settings / `.env` `CONTEXT_COMPACT_THRESHOLD`; rewrite uses `RemoveMessage(REMOVE_ALL_MESSAGES)` because `MessagesState` appends by default.
- **Q: Compact vs long-term memory?**  
  A: Compact = lossy **transcript** shrink; M8 stores facts/notes/project norms **outside** chat.
- Link: [M7](docs/milestones/M7-context-compaction.md)

### M8 — Project + long-term memory

- **Q: Why not only store the conversation in Postgres? Why Neo4j / vectors?**  
  A: Checkpointer already stores the **thread transcript**. Neo4j / pgvector / `AGENT.md` are **not** a second chat log — they survive compaction and new `thread_id`s.
- **Q: Four layers — what are they for?**  
  A: Transcript (checkpointer) | `AGENT.md` (auto file inject) | Fact/Neo4j (substring or latest-N) | Note/pgvector (semantic). Different failure modes if mixed.
- **Q: Fact vs Note — why not mix? Example?**  
  A: Hard exact truths (port `8080`, `pnpm`) → Fact; long paraphrase-friendly prose (“auth waits ~30s on Redis…”) → Note. Wrong store fails precision or recall-by-rewording.
- **Q: `inject_project_memory` — defined/called where?**  
  A: Defined in `agent/project_memory.py`; called from `graph._inject_memory_view` after compact, before `bound.invoke`.
- **Q: `recall_facts_block` — Cypher? Exact or semantic?**  
  A: Official Neo4j driver + **Cypher**. Match = case-insensitive **`CONTAINS`** (substring), **not** semantic. Auto-inject uses empty query = newest N Facts.
- **Q: `remember_note` — where / API? Is Postgres “faking” search? Why not Elasticsearch?**  
  A: Table `memory_notes`; **Ollama embeds** + **psycopg/SQL** + pgvector distance. Real vectors, not fake keyword search. ES = keyword/full-text at scale → parked **M21**, complementary not a replacement for embeddings.
- **Q: When is `remember_note` used? When is `build_memory_tools` called?**  
  A: Note tools only when the model calls them (user asks to store/recall prose). `build_memory_tools` runs **once at graph build** via `build_default_tools` — four tools. `@tool` ≈ `StructuredTool` for ToolNode; thin wrap over `memory/`.
- **Q: How to test?**  
  A: `./scripts/test.sh tests/unit/test_m8_*.py`; integration `test_m8_memory_live` / `test_m8_pgvector_live`; `./scripts/db-inspect.sh`; optional `ollama pull nomic-embed-text`.
- Later: M20 ingestion/chunking; M21 local Elasticsearch; M18/M19 channel → PR + quality gate.
- Link: [M8](docs/milestones/M8-project-long-term-memory.md)

---

## 2026-08-26 — Dig: confirm — explicit tool is our teaching choice

- **Q: So we explicitly `load_skill` via a tool; industry often uses internal markers/API/hybrids to inject into the prompt; and our tool is for teaching?**  
  A: **Yes.** Same progressive-disclosure idea (catalog always, body on demand). Mechanism differs: we expose activation as a normal tool_call for visibility/tests; many products hide selection+inject inside the prompt pipeline (markers, internal load API, matcher, or hybrid). Teaching > matching any one vendor’s private wiring.
- Link: M13 digs above

---

## 2026-08-26 — Dig: if not a tool call, who decides which skill to inject?

- **Q: Without a tool call, how does the agent know to inject a skill?**  
  A: **Inject is done by the host; “which skill” still needs a signal.** The catalog (name+description) is always in the prompt so the model *knows options*. Choosing the body is separate: (1) **explicit tool** (our `load_skill`) — clearest; (2) **model emits a structured cue** the harness parses (e.g. internal “use skill X”, not shown as a normal tool); (3) **non-LLM matcher** on the user message vs skill descriptions (keywords/embeddings) — host injects without the model choosing; (4) **hybrid**. There is no free lunch: something must select. Industry often hides (2)/(3) inside the prompt pipeline so you don’t see a `load_skill` tool_call; we expose (1) for learning.
- Link: M13, `agent/skills.py`

---

## 2026-08-26 — Dig: what “prompt pipeline inject” means

- **Q: What does prompt pipeline inject mean?**  
  A: Before each model call, the host **builds the message list** the LLM will see (system, history, tool results, extras). **Inject** = the runtime **inserts extra text into that list** without the model having issued a tool call for it. Our repo already does this for `AGENT.md`, Neo4j facts, and the skills **catalog** in `_inject_memory_view` / `inject_skills_view` — that *is* prompt-pipeline inject. Industry skill **bodies** often load the same way (host appends the SKILL.md text into the assembled prompt). Our skill **body** activation is different: model must call `load_skill` first (tool path); we only re-inject scanned bodies afterward.
- Link: `agent/graph.py` (`_inject_memory_view`), `agent/skills.py`, `agent/project_memory.py`

---

## 2026-08-26 — Dig: how we load skills vs industry inject

- **Q: We load via a tool — how does industry load? Straight into the system prompt?**  
  A: **We:** model calls `load_skill` → body returns as **ToolMessage** (and we may re-inject scanned bodies into the prompt view as SystemMessages). **Industry (typical):** host keeps a **catalog** in the always-on prompt; when a skill is selected (model intent and/or matcher), the runtime **reads `SKILL.md` and appends/injects that text into the context** for upcoming model calls — often as extra **system / developer / user-context blocks**, not necessarily as a tool result. So yes: closer to “add into the prompt assembly” than “tool round-trip,” though products differ on exact message role. Same progressive-disclosure goal.
- Link: `agent/skills.py`, M13

---

## 2026-08-26 — Dig: are Claude/Codex skills also tools?

- **Q: In Claude Code / Codex, is a skill also a tool like our `load_skill`?**  
  A: **Usually no (not as a user-visible tool).** Industry “skills” are mostly **progressive-disclosure instruction packs** (name+description always cheap; full `SKILL.md` body injected into context when relevant). Activation is often **runtime/prompt plumbing** (model picks from the catalog → host loads the file) — you may not see a `load_skill` tool_call in the transcript. Our M13 uses an explicit **`load_skill` StructuredTool** so the activation is visible and testable (teaching choice). Same *idea* (L0 catalog / L1 body); different *mechanism* (tool vs silent inject). Still distinct from subagents (nested agent loop).
- Link: [M13](docs/milestones/M13-skills-progressive-disclosure.md), `agent/skills.py`

---

## 2026-08-26 — M13: Skills progressive disclosure

- Insight: Catalog L0 always; `load_skill` L1 body; not a nested agent.
- Commands: `./scripts/test.sh tests/unit/test_m13_skills.py`
- Link: [docs/milestones/M13-skills-progressive-disclosure.md](docs/milestones/M13-skills-progressive-disclosure.md)

---

## 2026-08-26 — Dig: subagent is a tool, not a new parent node

- **Q: How does the subagent run — new graph node, or a tool? Why does `build_subagent_tools` return a list?**  
  A: **Tool, not a new parent node.** Parent topology stays `call_model` ↔ `tools`. `run_subagent` is a normal `StructuredTool`; when the parent model calls it, `ToolNode` runs the function, which **internally** `build_agent_graph(...).invoke(...)` for the child (nested graph, fresh messages). Returning `list[BaseTool]` matches every other builder (`build_coding_tools`, `build_shell_tools`, …) so `build_default_tools` can splat `*build_subagent_tools(...)`. Today the list has **one** tool (`run_subagent`); a list keeps the door open for “one tool per YAML name” later without changing the assembler. Not because LangGraph requires multiple tools.
- Link: `agent/subagents.py`, `tools/default.py`

---

## 2026-08-26 — M12: Sub-agents

- Insight: `run_subagent` → nested graph, isolated messages, YAML allowlist; parent topology unchanged.
- Commands: `./scripts/test.sh tests/unit/test_m12_subagents.py`
- Link: [docs/milestones/M12-sub-agents.md](docs/milestones/M12-sub-agents.md)

---

## 2026-08-26 — Dig: why HITL+git is not enough; where `--rm` lives

- **Q: Why aren’t git tools + HITL enough? When do we need Docker for shell?**  
  A: HITL answers “did a human approve?” — not “can this process hurt the host if approved or tricked.” `git_*` is a narrow VCS surface; `run_shell` is a **general command interpreter** (`shell=True`). Examples needing isolation even after approve: `curl … | bash`, `pip install` / native builds touching `$HOME`, reading `~/.ssh` or cloud creds via absolute paths, fork bombs / fill-disk, typos like `rm -rf /` (denylist is bypassable). Docker limits blast radius to the container + mounted workspace. Local Claude Code–class products often still lean on HITL; Docker/VM is defense-in-depth or cloud-default.
- **Q: Do we `rm` the container after each run? Where is the “callback”?**  
  A: **No Python callback.** Default path is `docker run --rm ...` — Docker itself deletes the container when the command exits. See `build_docker_run_argv` in `sandbox_docker.py` (`"--rm"` in argv). Per-command ephemeral sandbox (M11 simplification), not a long-lived sidecar.
- Link: [M11](docs/milestones/M11-docker-sandbox.md), `tools/sandbox_docker.py`

---

## 2026-08-26 — Dig: Claude Code / Codex sandbox vs our M11 Docker

- **Q: Do Claude Code / Codex also run in a sandbox? Is production just `docker run` like us?**  
  A: **Spectrum, not one pattern.** Local IDE agents (Claude Code, Cursor, Codex CLI on your machine) usually emphasize **permissions/HITL + host execution** (and sometimes **OS-level** sandbox: Seatbelt/seccomp/landlock) — not “every shell is `docker run --rm`.” **Cloud** coding agents (Codex cloud, hosted computer-use) typically get a **dedicated remote sandbox** (container or full VM / microVM) that lives for the session, with tooling preinstalled and controlled egress — closer to “isolated machine” than our per-command Docker.  
  **Our M11** teaches the isolation *idea* with the simplest durable primitive on a laptop: ephemeral Docker + workspace mount + `--network none`. Gaps vs production: long-lived sandbox vs per-command; OS sandbox / microVM vs Docker-on-Desktop; egress allowlists, non-root, seccomp, no docker.sock, audit; we still run `git_*` on host; local products still rely heavily on **ask/deny (our M9/M10)** even when a sandbox exists.  
  So: industry ≠ “always Docker process”; industry = **policy + (optional) OS/container/VM isolation**, with cloud agents stronger on isolation and local agents stronger on UX permissions.
- Link: [M11](docs/milestones/M11-docker-sandbox.md)

---

## 2026-08-26 — M11: Docker sandbox for shell

- Insight: `run_shell` → ephemeral Docker by default; host backend opt-in; graph unchanged.
- Commands: `./scripts/test.sh tests/unit/test_m11_sandbox.py`; integration needs Docker daemon.
- Link: [docs/milestones/M11-docker-sandbox.md](docs/milestones/M11-docker-sandbox.md)

---

## 2026-08-26 — Dig: where `__interrupt__` comes from

- **Q: Who produces `__interrupt__`, and how does `result_interrupt_values` see it?**  
  A: **LangGraph**, not our code. When the tool wrap calls `interrupt(payload)`, the runtime pauses, checkpoints, and the **`graph.invoke(...)` return dict** includes key `__interrupt__` — a sequence of `Interrupt` objects (`value` = our payload, plus an id). We never assign `result["__interrupt__"]` ourselves. `result_interrupt_values(result)` only reads that key and unwraps `.value`. Fallback: `pending_interrupt_values(graph, config)` reads `graph.get_state(config).interrupts` (same Pause info on the checkpoint). If there was no interrupt, both are empty.
- Link: `hitl.py` (`result_interrupt_values`, `pending_interrupt_values`); pause site `permissions.py` → `interrupt(...)`.

---

## 2026-08-26 — Dig: where invoke_with_hitl is called; why not middleware

- **Q: Where is `invoke_with_hitl` called?**  
  A: Only from `agent/cli.py` → `_run_once` (and thus REPL via `_run_repl`). Tests also call it directly (`test_m10_hitl*.py`). It is **not** imported by `graph.py` / `permissions.py`.
- **Q: Why not LangGraph middleware?**  
  A: Teaching/Option B choice: keep a **tiny ReAct graph** and put policy (`permissions` wrap) + HITL outer loop (`hitl.py`) where you can see them. Middleware can centralize pre/post tool hooks, but it hides the same ideas behind framework glue and was not required for M9/M10 learning goals. Later (hooks M15) we may revisit middleware-style lifecycle — still as an explicit dig, not magic.
- Call chain (CLI): `main` → `_build`/`build_agent_graph` (wrap tools) → `_run_once` → `invoke_with_hitl` → loop `graph.invoke` / `Command(resume)` → nodes → permission wrap → `interrupt`.
- Link: `cli.py`, `hitl.py`, `permissions.py`, `graph.py`

---

## 2026-08-25 — Dig: AskCallback always None in prod? How resume works

- **Q: Is `AskCallback` always `None` in production? Only for tests?**  
  A: **Yes for our CLI production path.** `cli.py` builds the graph with `ask_callback=None`. Unit tests may pass a lambda to bypass `interrupt` without a checkpointer. If someone called `build_agent_graph(ask_callback=...)` in a custom script, that would be a deliberate override — not the shipping CLI.
- **Q: How does `invoke_with_hitl` wrap `graph.invoke`, and how does resume work?**  
  A: It is a **while loop outside the graph**, not a graph node. (1) `payload = {messages: [...]}` → `graph.invoke(payload, config)`. (2) If result/`get_state` has `__interrupt__`, CLI `prompt_approval` → y/n. (3) `payload = Command(resume=bool)` → `graph.invoke(payload, config)` again. **LangGraph** stores the paused task in the **checkpointer** and, on `Command(resume=…)`, re-enters the interrupted tool wrap so `interrupt()` returns the bool. Our code: `agent/hitl.py` (`invoke_with_hitl`), CLI calls it from `_run_once`; pause site: `permissions._wrap_one` → `interrupt(...)`.
- Link: `hitl.py`, `cli.py`, `permissions.py`

---

## 2026-08-25 — Dig: HITL call chain (invoke_with_hitl vs interrupt vs ask_callback)

- **Q: How does `invoke_with_hitl` “apply into” the graph? Is ask_callback the first y/n and interrupt the second?**  
  A: **No.** They are not two steps of one approval.  
  - **`ask_callback`:** optional **test-only bypass**. If set, wrap never calls `interrupt` (sync True/False). Production CLI passes `ask_callback=None`.  
  - **Production ask:** wrap always hits `interrupt(payload)` → graph **pauses** (needs checkpointer). `invoke_with_hitl` is **outside** the graph: loop `graph.invoke` → see `__interrupt__` → print y/n → `graph.invoke(Command(resume=bool))`.  
  - **On resume:** LangGraph **re-enters the same wrap**, runs the **same** `interrupt(...)` line again; this time `interrupt()` **returns** the resume bool (does not pause again). Then tool body runs or deny. Your y/n is **not** `ask_callback` — it is CLI `prompt_approval` → `Command(resume=…)`.
- Call chain: `cli._run_once` → `invoke_with_hitl` → `graph.invoke` → `call_model` → `ToolNode` → permission wrap → `interrupt` → back to CLI → `Command(resume)` → wrap continues.
- Link: `agent/hitl.py`, `agent/permissions.py`, `agent/cli.py`

---

## 2026-08-25 — M10: Human-in-the-loop (`interrupt`)

- Insight: Ask → `interrupt` + checkpointer; resume → `Command(resume=bool)`. Policy plane from M9 unchanged.
- Insight: CLI HITL uses `invoke_with_hitl`; Plan Mode can still stream.
- Commands: `./scripts/test.sh tests/unit/test_m10_hitl.py`; `./scripts/agent.sh --checkpointer memory --no-stream "…"`
- Link: [docs/milestones/M10-human-in-the-loop-interrupt.md](docs/milestones/M10-human-in-the-loop-interrupt.md)

---

## 2026-08-25 — Dig: TTY vs ask_callback

- **Q: What is TTY? What is ask_callback?**  
  A: **TTY** = interactive terminal (you type at a prompt). `sys.stdin.isatty()` is True in a normal terminal session, False when stdin is a pipe/CI/script. **ask_callback** = a function `(tool_name, args) → bool` the permission wrap calls when mode is `ask`: True = run tool, False = deny. M9’s `make_cli_ask_callback` prints y/N and reads stdin — only useful on a TTY. Non-TTY → we pass `ask_callback=None` so ask becomes deny (no hung wait for input that will never come). M10 will replace this callback with LangGraph `interrupt` (durable pause, not stdin).
- Link: `agent/cli.py`, `agent/permissions.py`

---

## 2026-08-25 — Dig: who calls apply_permissions / make_cli_ask_callback

- **Q: Where are `apply_permissions` and `make_cli_ask_callback` called?**  
  A: `apply_permissions` → `build_agent_graph` in `agent/graph.py` (when `apply_tool_permissions=True`, default). Also unit tests. `make_cli_ask_callback` → `agent/cli.py` `main()` only when not Plan Mode and stdin is a TTY; that callback is passed into `build_agent_graph(..., ask_callback=...)`. Non-TTY / `--plan` → `ask_callback=None` → ask becomes deny inside the wrap.
- Link: `agent/graph.py`, `agent/cli.py`, `agent/permissions.py`

---

## 2026-08-25 — Dig: where permissions live + what the file does

- **Q: Is Plan Mode “wrapping permissions.py”?**  
  A: Almost inverted. `permissions.py` is the **policy module**. At graph build, `apply_permissions(...)` wraps **each tool**. Plan Mode is only a **flag** (`plan_mode=True` / `--plan`) passed into `resolve_permission` so mutators become `deny`. Same wrap path in normal mode (`ask`/`auto`); Plan Mode changes the *decision*, not a second wrapper type.
- **Q: Why under `agent/` not `tools/` or `policy/`?**  
  A: It is **runtime policy for this agent**, wired from `graph.py` / `cli.py`, not a FS/shell tool implementation. Option B “policy plane” still sits next to other agent runtime (`compact`, `project_memory`, checkpointer). A top-level `policy/` package would also be fine later if the folder grows; teaching shortcut = keep it beside the graph for now.
- **Q: What does `permissions.py` mainly do?**  
  A: (1) Classify tools read-safe vs mutating; (2) `resolve_permission` → `auto`/`ask`/`deny`; (3) `apply_permissions` wrap so ToolNode hits policy before the real body; (4) `make_cli_ask_callback` for TTY y/n (M9 simplification until M10 interrupt).
- Link: [M9](docs/milestones/M9-permissions-plan-mode.md), `agent/permissions.py`

---

## 2026-08-25 — M9: Permissions & Plan Mode

- Insight: Policy wraps tools before `ToolNode`; graph topology unchanged.
- Insight: Plan Mode = mutators `deny`; ask via TTY is a simplification until M10 `interrupt`.
- Commands: `./scripts/test.sh tests/unit/test_m9_permissions.py`; `./scripts/agent.sh --plan "…"`
- Link: [docs/milestones/M9-permissions-plan-mode.md](docs/milestones/M9-permissions-plan-mode.md)

---

## 2026-08-25 — Dig: why M9 skips path ACL / “always allow”

- **Q: Why not ship path ACL or “always allow this command” in M9?**  
  A: M9’s learning target is the **policy plane** (`auto`/`ask`/`deny` + Plan Mode) sitting *outside* the ReAct loop. Path ACL (“`write_file` only under `src/`”) and sticky grants (“always allow this shell”) are **product rules on top of that plane** — more tables, UX, and persistence — without teaching a new LangGraph idea. They also blur into M10 (session grants need durable resume) and M11 (sandbox is stronger than path strings). Do them later once the decision function + HITL pause exist; otherwise the milestone becomes a mini permission product and hides the Option B lesson.
- Link: [M9](docs/milestones/M9-permissions-plan-mode.md)

---

## 2026-08-25 — Process: auto Learning Log Q&A (rule landed)

- Standing rule in `.cursor/rules/learning-log-qa.mdc` (also milestones + collaboration rules): after review, and on conceptual digs, update this log without waiting for “please write it.”
- Cadence: finish milestone review → study this index → then next Plan.
- This index backfills M0–M8 Q→A from prior review chats.

---

## 2026-08-24 — M8-B: minimal pgvector notes

- Insight: **Fact (Neo4j)** = crisp truths; **Note (pgvector)** = fuzzy prose recall via embeddings — different tools on purpose.
- Commands: `ollama pull nomic-embed-text`; `./scripts/test.sh tests/integration/test_m8_pgvector_live.py`
- Link: [docs/milestones/M8-project-long-term-memory.md](docs/milestones/M8-project-long-term-memory.md)

---

## 2026-08-24 — M8: Project + long-term memory

- Insight: Checkpointer (Postgres) = **this thread’s chat**; `AGENT.md` = always-on project norms; Neo4j = **durable facts** across threads — not a second chat log.
- Insight: compact → inject → invoke keeps Option B; tools `remember_fact` / `recall_facts` write/read Neo4j.
- Vectors: initially docs-only (A); **B follow-on** adds `remember_note` / `recall_notes`.
- Commands: `./scripts/test.sh tests/unit/test_m8_memory.py`; `./scripts/db-inspect.sh neo4j`
- Link: [docs/milestones/M8-project-long-term-memory.md](docs/milestones/M8-project-long-term-memory.md)

---

## 2026-08-24 — Future digs: M20 ingestion pipeline + M21 Elasticsearch

- Idea: after thin M8 memory, add **local production-ish** improvements (few users → Docker Compose on a laptop is fine).
- **M20:** chunking/cleaning pipeline feeding Neo4j/pgvector (ingestion ≠ “Neo4j cuts text by itself”).
- **M21:** add Elasticsearch for full-text/keyword search; teach ES vs graph vs vectors.
- Not in current M8 scope — parked in [docs/ROADMAP.md](docs/ROADMAP.md).

---

## 2026-08-24 — M7: Context compaction

- Insight: Durable sessions (M5) without compaction are a footgun — context grows until the provider breaks or quality dies.
- Insight: Compaction ≠ long-term memory (M8): lossy compression of the *live transcript*, done in the policy plane before `call_model`.
- Insight: `MessagesState` appends — rewriting history needs `RemoveMessage(REMOVE_ALL_MESSAGES)`.
- Commands: `./scripts/test.sh tests/unit/test_m7_compaction.py`; set low `CONTEXT_COMPACT_THRESHOLD` to demo.
- Link: [docs/milestones/M7-context-compaction.md](docs/milestones/M7-context-compaction.md)

---

## 2026-08-24 — Future dig: pre-ship quality gate (M19) + tighten M18

- Idea: Slack/Discord may drive work, but **no PR/push until format + all tests are green**; on failure the agent keeps fixing (bounded loop). Repo **owner** may push; otherwise open a PR.
- Split: M18 = channel adapter → agent; **M19** = reusable ship gate (format/test/fix-until-green + pr vs push policy).
- Parked in [docs/ROADMAP.md](docs/ROADMAP.md); depends on M9/M10 permissions/HITL in practice.

---

## 2026-08-24 — Rename stream helper to `stream_render`

- Insight: `stream_cli` sounded like a second entrypoint; it only **renders** `graph.stream` events for `cli.py`.
- Change: `agent/stream_cli.py` → `agent/stream_render.py`.

---

## 2026-08-23 — M6: Streaming CLI

- Insight: Streaming is **when** you see events, not a smarter agent — final state matches `invoke`.
- Insight: Pass **`config` into `model.invoke(..., config)`** inside `call_model`; bare invoke / non-callback fakes will not feed `stream_mode="messages"`.
- Insight: Tokens ≠ tool progress — use `updates` (or later `custom`) for tool lifecycle.
- Commands: `./scripts/agent.sh "…"` vs `--no-stream`; `./scripts/test.sh tests/unit/test_m6_streaming.py`
- Link: [docs/milestones/M6-streaming-cli.md](docs/milestones/M6-streaming-cli.md)

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
