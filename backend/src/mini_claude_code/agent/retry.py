"""LLM invoke retries with exponential backoff (M17 / M22 async).

Wraps ``call_model``'s ``bound.invoke`` / ``ainvoke`` (and compaction summarizer).
Does not retry tool/MCP bodies or HITL decisions — those are different failure modes.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from mini_claude_code.config import Settings, get_settings

T = TypeVar("T")


def is_transient_llm_error(exc: BaseException) -> bool:
    """True for rate limits, timeouts, and connection-style failures."""
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in {
        101,  # network unreachable
        104,  # connection reset
        110,  # timeout
        111,  # connection refused (gateway blip)
    }:
        return True
    name = type(exc).__name__
    if any(
        token in name
        for token in (
            "RateLimit",
            "Timeout",
            "ServiceUnavailable",
            "APIConnection",
            "InternalServer",
        )
    ):
        return True
    # LangChain / vendor wrappers sometimes nest the real error.
    cause = exc.__cause__
    if cause is not None and cause is not exc:
        return is_transient_llm_error(cause)
    return False


def invoke_with_retry(
    invoke: Callable[[], T],
    *,
    settings: Settings | None = None,
    max_attempts: int | None = None,
    backoff_sec: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``invoke``; retry transient LLM errors with exponential backoff."""
    settings = settings or get_settings()
    attempts = max(1, max_attempts if max_attempts is not None else settings.llm_max_retries)
    base = backoff_sec if backoff_sec is not None else settings.llm_retry_backoff_sec
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return invoke()
        except Exception as exc:
            if not is_transient_llm_error(exc):
                raise
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            delay = min(base * (2**attempt), 60.0)
            sleep(delay)
    assert last_exc is not None
    raise last_exc


async def ainvoke_with_retry(
    ainvoke: Callable[[], Awaitable[T]],
    *,
    settings: Settings | None = None,
    max_attempts: int | None = None,
    backoff_sec: float | None = None,
) -> T:
    """Async twin of ``invoke_with_retry`` (uses ``asyncio.sleep``)."""
    settings = settings or get_settings()
    attempts = max(1, max_attempts if max_attempts is not None else settings.llm_max_retries)
    base = backoff_sec if backoff_sec is not None else settings.llm_retry_backoff_sec
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await ainvoke()
        except Exception as exc:
            if not is_transient_llm_error(exc):
                raise
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            delay = min(base * (2**attempt), 60.0)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
