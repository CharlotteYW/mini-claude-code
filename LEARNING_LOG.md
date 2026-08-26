# Learning Log

Dated entries after each completed milestone. Keep entries short; full detail lives in `docs/milestones/`.

**Order: newest first** (reverse chronological). Always prepend new dated entries below the process note / Q&A index.

## Process (standing rule)

1. After a milestone ships and you finish chat review/Q&A → concepts go here (English).
2. Before the next milestone Plan → re-read that milestone’s section in the **Concept Q&A index**; ask remaining questions; then approve the next Plan.
3. Mentor/agent must update this log for review Q&A **without being asked** (Cursor rule: `.cursor/rules/learning-log-qa.mdc`).
4. Milestone **Results** = what we built; this file = **what you understand** (including doubts you had and the answers).

---

## Concept Q&A index (M0–M11 study guide)

Study this before starting M12. Links point at full milestone docs.

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
