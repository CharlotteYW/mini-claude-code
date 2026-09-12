"""Observability traces sidecar (M34).

Stream (M6) = live UX. Usage footer (M17) = local totals. Checkpoints (M31) =
session time-travel. Traces = durable **LLM → tool → LLM** span trees for
postmortems.

Primary sink: LangSmith via env opt-in (``LANGCHAIN_TRACING_V2`` + API key).
Offline teaching: optional JSONL callback (``JsonlTraceHandler``).
Topology unchanged — enrich ``RunnableConfig`` + callbacks only.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig

from mini_claude_code.config import Settings

# Obvious secret-ish substrings for metadata redaction (teaching, not a WAF).
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9\-_]{8,})\b"),
    re.compile(r"(?i)\b(Bearer\s+[A-Za-z0-9\-._~+/]+=*)"),
    re.compile(r"(?i)\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"),
)

_REDACTED = "[REDACTED]"


_SECRET_KEY_HINTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "passwd",
)


def redact_secrets(text: str) -> str:
    """Strip common secret shapes from a string (metadata / JSONL fields)."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


def _key_looks_secret(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(h in lowered for h in _SECRET_KEY_HINTS)


def redact_value(value: Any) -> Any:
    """Redact strings; recurse into dict/list for metadata maps.

    Dict values whose **keys** look secret-ish are fully redacted.
    """
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if _key_looks_secret(key) and v not in (None, ""):
                out[key] = _REDACTED
            else:
                out[key] = redact_value(v)
        return out
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value(v) for v in value)
    return value


def langsmith_env_enabled() -> bool:
    """True when LangSmith tracing env flags look opted-in."""
    for key in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        raw = (os.environ.get(key) or "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
    return False


def langsmith_api_key_present() -> bool:
    return bool(
        (os.environ.get("LANGSMITH_API_KEY") or "").strip()
        or (os.environ.get("LANGCHAIN_API_KEY") or "").strip()
    )


def langsmith_project() -> str:
    return (
        (os.environ.get("LANGSMITH_PROJECT") or "").strip()
        or (os.environ.get("LANGCHAIN_PROJECT") or "").strip()
        or "mini-claude-code"
    )


@dataclass(frozen=True)
class TracingStatus:
    langsmith_flag: bool
    api_key_present: bool
    project: str
    local_path: str | None = None

    @property
    def langsmith_active(self) -> bool:
        return self.langsmith_flag and self.api_key_present

    def banner_lines(self) -> list[str]:
        lines: list[str] = []
        if self.langsmith_active:
            lines.append(
                f"  tracing:      langsmith on (project={self.project!r})"
            )
        elif self.langsmith_flag and not self.api_key_present:
            lines.append(
                "  tracing:      langsmith flag set but no API key "
                "(LANGSMITH_API_KEY)"
            )
        else:
            lines.append("  tracing:      off (set LANGCHAIN_TRACING_V2=true + key)")
        if self.local_path:
            lines.append(f"  trace_jsonl:  {self.local_path}")
        return lines


def tracing_status(*, local_path: str | None = None) -> TracingStatus:
    path = (local_path or "").strip() or None
    return TracingStatus(
        langsmith_flag=langsmith_env_enabled(),
        api_key_present=langsmith_api_key_present(),
        project=langsmith_project(),
        local_path=path,
    )


def enrich_run_config(
    config: RunnableConfig | dict[str, Any],
    *,
    settings: Settings | None = None,
    thread_id: str | None = None,
    run_name: str = "mcc-agent",
    extra_tags: Sequence[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> RunnableConfig:
    """Stamp tags/metadata/run_name for LangSmith correlation (mutates copy).

    Does not enable tracing by itself — env opt-in does. Safe when tracing off.
    """
    cfg: dict[str, Any] = dict(config or {})
    tags = list(cfg.get("tags") or [])
    for t in ("mini-claude-code", "m34-trace"):
        if t not in tags:
            tags.append(t)
    if extra_tags:
        for t in extra_tags:
            if t and t not in tags:
                tags.append(str(t))
    cfg["tags"] = tags
    cfg["run_name"] = cfg.get("run_name") or run_name

    meta: dict[str, Any] = dict(cfg.get("metadata") or {})
    conf = dict(cfg.get("configurable") or {})
    tid = thread_id or conf.get("thread_id")
    if tid:
        meta.setdefault("thread_id", str(tid))
    if settings is not None:
        meta.setdefault("llm_provider", settings.llm_provider)
        meta.setdefault("llm_model", settings.llm_model)
    if extra_metadata:
        meta.update(extra_metadata)
    cfg["metadata"] = redact_value(meta)
    return cfg  # type: ignore[return-value]


@dataclass
class SpanEvent:
    """One local teaching span/event (not a full OTel exporter)."""

    name: str
    kind: str  # run | llm | tool
    parent: str | None = None
    status: str = "ok"
    detail: str = ""


def span_tree_lines(events: Sequence[SpanEvent]) -> list[str]:
    """Render a tiny ASCII tree for Learning Log / unit demos."""
    by_parent: dict[str | None, list[SpanEvent]] = {}
    for ev in events:
        by_parent.setdefault(ev.parent, []).append(ev)
    lines: list[str] = []

    def walk(parent: str | None, indent: int) -> None:
        for ev in by_parent.get(parent, []):
            pad = "  " * indent
            extra = f" ({ev.detail})" if ev.detail else ""
            lines.append(f"{pad}- [{ev.kind}] {ev.name}{extra}")
            walk(ev.name, indent + 1)

    walk(None, 0)
    return lines


class JsonlTraceHandler(BaseCallbackHandler):
    """Append redacted span-ish events to a JSONL file (offline teaching)."""

    def __init__(self, path: str | Path, *, run_id: str | None = None) -> None:
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or str(uuid4())
        self._stack: list[str] = []
        self._write(
            {
                "event": "run_start",
                "run_id": self.run_id,
                "ts": time.time(),
            }
        )

    def _write(self, payload: dict[str, Any]) -> None:
        line = json.dumps(redact_value(payload), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[Any],
        *,
        run_id: Any,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or "chat_model"
        self._stack.append(str(run_id))
        self._write(
            {
                "event": "llm_start",
                "run_id": self.run_id,
                "span_id": str(run_id),
                "parent_span_id": str(parent_run_id) if parent_run_id else None,
                "name": name,
                "ts": time.time(),
            }
        )

    def on_chat_model_end(
        self,
        response: Any,
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> Any:
        self._write(
            {
                "event": "llm_end",
                "run_id": self.run_id,
                "span_id": str(run_id),
                "ts": time.time(),
            }
        )
        if self._stack and self._stack[-1] == str(run_id):
            self._stack.pop()
        return None

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> Any:
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        self._write(
            {
                "event": "tool_start",
                "run_id": self.run_id,
                "span_id": str(run_id),
                "parent_span_id": str(parent_run_id) if parent_run_id else None,
                "name": str(name),
                "input": input_str[:500] if isinstance(input_str, str) else "",
                "ts": time.time(),
            }
        )
        return None

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> Any:
        text = str(output)
        self._write(
            {
                "event": "tool_end",
                "run_id": self.run_id,
                "span_id": str(run_id),
                "output": text[:500],
                "ts": time.time(),
            }
        )
        return None

    def close_run(self, *, status: str = "ok", extra: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "event": "run_end",
            "run_id": self.run_id,
            "status": status,
            "ts": time.time(),
        }
        if extra:
            payload["extra"] = extra
        self._write(payload)


def attach_callbacks(
    config: RunnableConfig | dict[str, Any],
    *handlers: BaseCallbackHandler,
) -> RunnableConfig:
    """Append callback handlers onto a run config."""
    cfg: dict[str, Any] = dict(config or {})
    existing = list(cfg.get("callbacks") or [])
    existing.extend(handlers)
    cfg["callbacks"] = existing
    return cfg  # type: ignore[return-value]


def contrast_blurb() -> str:
    return (
        "stream=live UX; --usage=local token footer; traces=LLM/tool span tree "
        "(LangSmith or JSONL); checkpoints=session time-travel."
    )


__all__ = [
    "JsonlTraceHandler",
    "SpanEvent",
    "TracingStatus",
    "attach_callbacks",
    "contrast_blurb",
    "enrich_run_config",
    "langsmith_api_key_present",
    "langsmith_env_enabled",
    "langsmith_project",
    "redact_secrets",
    "redact_value",
    "span_tree_lines",
    "tracing_status",
]
