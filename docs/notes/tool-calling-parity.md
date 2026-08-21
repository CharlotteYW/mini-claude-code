# Tool-calling & chat-message compatibility (M1 notes)

This note answers: with multiple providers/models, how do we keep **tool call**
and **chat message** formats compatible?

## Short answer

We do **not** hand-roll four wire formats in agent code.

| Layer | What we write | Who adapts |
|---|---|---|
| Agent-facing messages | LangChain `HumanMessage` / `AIMessage` / `ToolMessage` / `SystemMessage` | Each `langchain-*` provider package serializes to its HTTP API |
| Tools | One `@tool` (JSON schema from the function signature + docstring) | `bind_tools` asks the provider adapter to attach vendor-shaped tool defs |
| Tool calls in responses | Read `AIMessage.tool_calls` (normalized) | Adapter maps Anthropic `tool_use` blocks or OpenAI `tool_calls` into that field |

M2’s StateGraph will **store and route these LangChain messages**. It does not
replace the compatibility layer — it consumes it via `create_chat_model()`.

## Protocol families (mental model)

```text
                    ┌─────────────────────────┐
 Agent code         │ LangChain messages +    │
                    │ AIMessage.tool_calls    │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
 ChatAnthropic            ChatOpenAI              ChatOllama
 (Anthropic Messages)     (OpenAI tools)          (local OpenAI-ish)
        │                       │
        │                       ├── OpenAI official
        │                       └── OpenRouter (same protocol, gateway URL)
        ▼                       ▼
 tool_use / tool_result    tools + tool_calls
 content blocks            on the message object
```

**Provider ≠ model ≠ protocol.** Claude via Anthropic-native vs Claude via
OpenRouter may share a *model family* but not the same client path.

## What LangChain guarantees (approximately)

- You can write one tool and call `model.bind_tools([add])` for each provider.
- Successful tool-using replies expose `AIMessage.tool_calls` with `name` / `args` / `id`.
- You continue the conversation with `ToolMessage(tool_call_id=..., content=...)`.

## What still leaks (why this harness exists)

- Parallel tool calls, strict JSON schema, refusal-to-call-tools.
- Gemma 4 **thinking channels**: internal thought text must not be replayed as
  assistant history the same way as final answers (see Ollama Gemma 4 docs).
- OpenRouter quality depends on the **routed** upstream model’s tool support.
- Content may still include provider-specific structures (e.g. list content
  blocks on Anthropic) even when `tool_calls` is normalized — inspect both.

## How to re-run

```bash
./scripts/parity.sh                  # all configured providers
./scripts/parity.sh --provider ollama
./scripts/parity.sh --provider anthropic --model claude-sonnet-4-20250514
```

Missing API keys → `SKIP` (not a hard failure for that provider).

## Observed results (2026-08-20)

### Ollama / gemma4:31b

- Status: **PASS** (tool call + ToolMessage round-trip)
- Normalized call: `add(a=17, b=25)` with a stable `id`
- `AIMessage.content` was empty string on the tool-call turn; the call lived entirely in `tool_calls`. Final round-trip reply: `The sum of 17 and 25 is 42.`
- Takeaway: agent loops must key off `tool_calls`, not assume natural-language content on the same turn.

### Anthropic

- Status: **SKIP** (`ANTHROPIC_API_KEY` not set)
- Expected wire difference when enabled: tool use arrives as content blocks (`tool_use`); LangChain still fills `AIMessage.tool_calls`.

### OpenAI

- Status: **SKIP** (`OPENAI_API_KEY` not set)
- Expected: OpenAI-style `tool_calls` on the assistant message; closest to what Ollama exposes locally.

### OpenRouter

- Status: **SKIP** (`OPENROUTER_API_KEY` not set)
- Expected: same client path as OpenAI (`ChatOpenAI` + gateway); behavior follows the routed model.
