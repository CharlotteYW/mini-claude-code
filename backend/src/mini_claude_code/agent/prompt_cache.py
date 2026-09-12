"""Provider prompt-cache helpers (M37).

Anthropic supports ``cache_control`` breakpoints on content blocks (and an
invoke-level ``cache_control`` kwarg). OpenAI-compatible / Ollama paths are
intentional no-ops — do not invent a fake universal cache API.

Simplification: we mark the last leading SystemMessage (stable AGENT.md / facts
prefix) for Anthropic; we do not manage TTL or tool-definition breakpoints.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

from mini_claude_code.config import ProviderName

CACHE_CONTROL_EPHEMERAL: dict[str, str] = {"type": "ephemeral"}


def supports_prompt_cache(provider: ProviderName | str) -> bool:
    """True when this codebase knows how to attach cache breakpoints."""
    return str(provider) == "anthropic"


def invoke_kwargs_for_prompt_cache(
    provider: ProviderName | str,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    """Kwargs for ``chat_model.invoke(..., **kwargs)``.

    Anthropic: pass top-level ``cache_control`` so the API can move the
    breakpoint with the conversation. Other providers: empty dict.
    """
    if not enabled or not supports_prompt_cache(provider):
        return {}
    return {"cache_control": dict(CACHE_CONTROL_EPHEMERAL)}


def _with_cache_control_on_text(content: Any) -> Any:
    """Attach ephemeral cache_control to the last text block (or wrap a string)."""
    cc = dict(CACHE_CONTROL_EPHEMERAL)
    if isinstance(content, str):
        if not content:
            return content
        return [{"type": "text", "text": content, "cache_control": cc}]
    if isinstance(content, list) and content:
        blocks = list(content)
        last = blocks[-1]
        if isinstance(last, str):
            blocks[-1] = {"type": "text", "text": last, "cache_control": cc}
        elif isinstance(last, dict):
            blocks[-1] = {**last, "cache_control": cc}
        else:
            return content
        return blocks
    return content


def mark_stable_prefix_for_cache(
    messages: Sequence[BaseMessage],
    *,
    provider: ProviderName | str,
    enabled: bool = True,
) -> list[BaseMessage]:
    """Copy messages; for Anthropic, mark the last leading SystemMessage.

    Leading = contiguous SystemMessages at the start of the prompt view
    (project memory / skills / facts). Non-Anthropic → identity copy.
    """
    out = list(messages)
    if not enabled or not supports_prompt_cache(provider) or not out:
        return out

    last_sys = -1
    for i, msg in enumerate(out):
        if isinstance(msg, SystemMessage):
            last_sys = i
            continue
        break
    if last_sys < 0:
        return out

    original = out[last_sys]
    assert isinstance(original, SystemMessage)
    new_content = _with_cache_control_on_text(original.content)
    if new_content is original.content:
        return out
    out[last_sys] = SystemMessage(content=new_content)
    return out
