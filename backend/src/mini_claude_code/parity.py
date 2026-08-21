"""Cross-provider tool-calling parity harness (M1).

How format compatibility works (the point of this milestone):

1. **Chat messages (agent-facing):** we always speak LangChain message objects
   (`HumanMessage`, `AIMessage`, `ToolMessage`, …). Each provider package
   serializes those to its wire format (Anthropic content blocks vs OpenAI
   messages array) and deserializes responses back.

2. **Tool calls:** we define tools once (`@tool` / JSON schema). `bind_tools`
   asks the *provider adapter* to attach that schema in the vendor's shape.
   Responses are normalized onto `AIMessage.tool_calls` so the agent loop does
   not branch on Anthropic vs OpenAI.

3. **What is NOT guaranteed:** quirks still leak (parallel tools, strict JSON
   schema, Gemma thinking channels, OpenRouter upstream variance). This harness
   surfaces those differences instead of pretending they do not exist.

M2 will store these same LangChain messages in a StateGraph — it does not
replace this compatibility layer; it consumes it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude_code.config import ProviderName, Settings, get_settings
from mini_claude_code.llm import create_chat_model
from mini_claude_code.tools import add, demo_tools

Prompt = (
    "You must use the add tool to compute 17 + 25. "
    "Do not compute the sum yourself; call the tool."
)

ProviderChoice = ProviderName | Literal["all-configured"]


@dataclass
class ProbeResult:
    provider: str
    model: str
    status: Literal["PASS", "FAIL", "SKIP"]
    detail: str
    tool_calls: list[dict[str, Any]] | None = None


def _load_dotenv_from_repo_root() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _provider_ready(settings: Settings, provider: ProviderName) -> str | None:
    """Return SKIP reason, or None if we should attempt the provider."""
    if provider == "ollama":
        return None
    if provider == "anthropic" and not settings.anthropic_api_key:
        return "ANTHROPIC_API_KEY not set"
    if provider == "openai" and not settings.openai_api_key:
        return "OPENAI_API_KEY not set"
    if provider == "openrouter" and not settings.openrouter_api_key:
        return "OPENROUTER_API_KEY not set"
    return None


def _default_model_for(provider: ProviderName, settings: Settings) -> str:
    """When probing --all-configured, avoid sending gemma4:31b to cloud APIs."""
    if settings.llm_provider == provider:
        return settings.llm_model
    if provider == "ollama":
        return "gemma4:31b"
    if provider == "anthropic":
        return "claude-sonnet-4-20250514"
    if provider == "openai":
        return "gpt-4.1-mini"
    if provider == "openrouter":
        return "anthropic/claude-sonnet-4"
    return settings.llm_model


def _summarize_content(content: Any) -> str:
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, default=str)
    text = text.replace("\n", " ")
    return text if len(text) <= 240 else text[:237] + "..."


def _normalize_tool_calls(message: AIMessage) -> list[dict[str, Any]]:
    calls = []
    for tc in message.tool_calls or []:
        calls.append(
            {
                "name": tc.get("name"),
                "args": tc.get("args"),
                "id": tc.get("id"),
            }
        )
    return calls


def probe_provider(
    settings: Settings,
    provider: ProviderName,
    *,
    model: str | None = None,
    round_trip: bool = True,
    llm: Any | None = None,
) -> ProbeResult:
    """Probe one provider. Pass `llm` to inject a fake model (unit tests)."""
    skip = _provider_ready(settings, provider)
    model_name = model or _default_model_for(provider, settings)
    if skip and llm is None:
        return ProbeResult(provider, model_name, "SKIP", skip)

    try:
        chat = llm or create_chat_model(
            settings, provider=provider, model=model_name
        )
        bound = chat.bind_tools(demo_tools())
        first = bound.invoke([HumanMessage(content=Prompt)])
        if not isinstance(first, AIMessage):
            return ProbeResult(
                provider,
                model_name,
                "FAIL",
                f"expected AIMessage, got {type(first).__name__}",
            )

        tool_calls = _normalize_tool_calls(first)
        if not tool_calls:
            return ProbeResult(
                provider,
                model_name,
                "FAIL",
                "no tool_calls on AIMessage; "
                f"content={_summarize_content(first.content)!r}",
                tool_calls=[],
            )

        detail_parts = [
            f"tool_calls={json.dumps(tool_calls, default=str)}",
            f"raw_content={_summarize_content(first.content)!r}",
        ]

        if round_trip:
            # Execute tools locally and continue the chat with ToolMessage(s).
            # This is the same message cycle M2 will put inside a StateGraph.
            tool_messages: list[ToolMessage] = []
            for tc in first.tool_calls:
                name = tc["name"]
                if name != add.name:
                    return ProbeResult(
                        provider,
                        model_name,
                        "FAIL",
                        f"unexpected tool {name!r}; {detail_parts[0]}",
                        tool_calls=tool_calls,
                    )
                result = add.invoke(tc["args"])
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"],
                        name=name,
                    )
                )
            second = bound.invoke(
                [HumanMessage(content=Prompt), first, *tool_messages]
            )
            detail_parts.append(
                f"round_trip_content={_summarize_content(getattr(second, 'content', second))!r}"
            )

        return ProbeResult(
            provider, model_name, "PASS", "; ".join(detail_parts), tool_calls
        )
    except Exception as exc:  # noqa: BLE001 — harness must surface provider errors
        return ProbeResult(provider, model_name, "FAIL", f"{type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe tool-calling parity across LLM providers."
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "anthropic", "openai", "openrouter", "all-configured"],
        default="all-configured",
        help="Provider to probe (default: all-configured).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model id for a single --provider run.",
    )
    parser.add_argument(
        "--no-round-trip",
        action="store_true",
        help="Only check the first tool call; skip ToolMessage follow-up.",
    )
    args = parser.parse_args(argv)

    _load_dotenv_from_repo_root()
    get_settings.cache_clear()
    settings = get_settings()

    if args.provider == "all-configured":
        providers: list[ProviderName] = [
            "ollama",
            "anthropic",
            "openai",
            "openrouter",
        ]
    else:
        providers = [args.provider]  # type: ignore[list-item]

    print("mini-claude-code tool-calling parity (M1)")
    print(f"  prompt: {Prompt}")
    print()

    results: list[ProbeResult] = []
    for provider in providers:
        model = args.model if args.provider != "all-configured" else None
        result = probe_provider(
            settings,
            provider,
            model=model,
            round_trip=not args.no_round_trip,
        )
        results.append(result)
        print(f"[{result.status}] {result.provider} / {result.model}")
        print(f"       {result.detail}")
        print()

    failed = [r for r in results if r.status == "FAIL"]
    passed = [r for r in results if r.status == "PASS"]
    skipped = [r for r in results if r.status == "SKIP"]
    print(
        f"summary: PASS={len(passed)} FAIL={len(failed)} SKIP={len(skipped)}"
    )

    # Success if at least one provider passed and none failed among attempted.
    if failed:
        return 1
    if not passed:
        print(
            "ERROR: no provider PASS'd. Configure Ollama or an API key.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
