# Testing strategy

Every milestone **Plans and implements** tests for the code it adds. Tests are part of learning documentation: reading them should recall *how the feature is supposed to behave*.

## Layers

| Layer | Runs against | Marker | Purpose |
|---|---|---|---|
| **Unit** | In-process, no network, no Docker required | default / `@pytest.mark.unit` | Factory branching, tool schema, pure helpers, graph topology with fakes |
| **Integration** | Real Ollama and/or cloud APIs and/or Compose services | `@pytest.mark.integration` | Provider round-trips, checkpointer resume, sandbox, MCP |

## Rules

1. **Plan section required:** each `docs/milestones/M<N>-*.md` must include **Testing (planned)** with concrete unit + integration cases *before* coding approval.
2. **Done requires green unit tests** for that milestone’s new code.
3. **Integration tests** must be written in the same milestone; they may `@pytest.mark.skip` / skip when credentials or services are missing, but the test *file and cases* exist and document the contract.
4. Prefer testing shared helpers used by CLIs (`probe_provider`, `create_chat_model`) over scraping CLI stdout only.
5. Do not duplicate three sources of truth: CLI demos (`parity.sh`) can call the same functions tests call.

## Layout

```text
backend/tests/
  unit/
  integration/
  conftest.py
```

Run:

```bash
cd backend && uv run pytest -m unit
cd backend && uv run pytest -m integration   # needs services/keys as applicable
```

## Retroactive debt (M0 / M1)

**Cleared:** pytest suites under `backend/tests/` cover M0 factory/settings + Compose reachability and M1 tool/parity helpers + live Ollama probe. Cloud provider integration tests skip without API keys.
