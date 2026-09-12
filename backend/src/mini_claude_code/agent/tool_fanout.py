"""Tools fan-out policy (M32) + observation budgets (M39).

LangGraph ``ToolNode`` already fans out multi-``tool_calls`` (async gather /
sync thread pool). This module **owns the policy**:

- default: keep that parallel path (latency win on independent auto tools)
- ``TOOL_PARALLEL=false`` / ``--serial-tools``: force serial A/B baseline
- any ``ask`` tool in the batch → **serial** that step (HITL must not race)
- explicit ``handle_tool_errors`` so one failure still yields sibling ToolMessages
- M39: after combine, enforce ``TOOL_OBSERVATION_MAX_CHARS`` (head+tail / optional summarize)

Wrap onion (permissions / hooks / content policy) is unchanged — still per call;
observation budget runs on the **combined ToolMessages** entering graph state.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import get_config_list
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolRuntime, get_executor_for_config
from langgraph.runtime import Runtime
from pydantic import BaseModel

from mini_claude_code.agent.observation_budget import (
    Summarizer,
    apply_budget_to_tool_outputs,
)
from mini_claude_code.agent.permissions import resolve_permission

FanoutMode = Literal["parallel", "serial"]


def batch_needs_serial(
    tool_calls: list[Any],
    *,
    parallel: bool,
    plan_mode: bool,
) -> bool:
    """True when this tools step must run one call at a time."""
    if not parallel:
        return True
    for call in tool_calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        if resolve_permission(str(name), plan_mode=plan_mode) == "ask":
            return True
    return False


class PolicyToolNode(ToolNode):
    """ToolNode with fan-out policy + observation budget + ``last_mode``."""

    def __init__(
        self,
        tools: Any,
        *,
        parallel: bool = True,
        plan_mode: bool = False,
        max_concurrency: int | None = None,
        observation_max_chars: int = 0,
        observation_summarize: bool = False,
        observation_head_ratio: float = 0.6,
        observation_summarizer: Summarizer | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("handle_tool_errors", True)
        # Set before super so bound _func/_afunc see attributes if needed.
        self._parallel = bool(parallel)
        self._plan_mode = bool(plan_mode)
        self._max_concurrency = (
            int(max_concurrency) if max_concurrency and max_concurrency > 0 else None
        )
        self._observation_max_chars = int(observation_max_chars)
        self._observation_summarize = bool(observation_summarize)
        self._observation_head_ratio = float(observation_head_ratio)
        self._observation_summarizer = observation_summarizer
        self.last_mode: FanoutMode | None = None
        super().__init__(tools, **kwargs)

    def _apply_observation_budget(self, outputs: Any) -> Any:
        return apply_budget_to_tool_outputs(
            outputs,
            max_chars=self._observation_max_chars,
            head_ratio=self._observation_head_ratio,
            summarize=self._observation_summarize,
            summarizer=self._observation_summarizer,
            messages_key=getattr(self, "_messages_key", "messages"),
        )

    def _combine_tool_outputs(self, outputs: Any, input_type: Any) -> Any:
        combined = super()._combine_tool_outputs(outputs, input_type)
        return self._apply_observation_budget(combined)

    def _inject_concurrency(self, config: RunnableConfig) -> RunnableConfig:
        if self._max_concurrency is None:
            return config
        cfg = dict(config or {})
        cfg.setdefault("max_concurrency", self._max_concurrency)
        return cfg  # type: ignore[return-value]

    def _build_runtimes(
        self,
        input: Any,
        tool_calls: list[Any],
        config: RunnableConfig,
        runtime: Runtime,
    ) -> list[ToolRuntime]:
        config_list = get_config_list(config, len(tool_calls))
        tool_runtimes: list[ToolRuntime] = []
        for call, cfg in zip(tool_calls, config_list, strict=False):
            state = self._extract_state(input, cfg)
            tool_runtimes.append(
                ToolRuntime(
                    state=state,
                    tool_call_id=call["id"],
                    config=cfg,
                    context=runtime.context,
                    store=runtime.store,
                    stream_writer=runtime.stream_writer,
                    tools=list(self.tools_by_name.values()),
                    execution_info=runtime.execution_info,
                    server_info=runtime.server_info,
                )
            )
        return tool_runtimes

    def _func(
        self,
        input: list[Any] | dict[str, Any] | BaseModel,
        config: RunnableConfig,
        runtime: Runtime,
    ) -> Any:
        tool_calls, input_type = self._parse_input(input)
        config = self._inject_concurrency(config)
        serial = batch_needs_serial(
            list(tool_calls),
            parallel=self._parallel,
            plan_mode=self._plan_mode,
        )
        self.last_mode = "serial" if serial else "parallel"
        tool_runtimes = self._build_runtimes(input, list(tool_calls), config, runtime)
        if serial:
            outputs = [
                self._run_one(call, input_type, tr)
                for call, tr in zip(tool_calls, tool_runtimes, strict=False)
            ]
            return self._combine_tool_outputs(outputs, input_type)

        input_types = [input_type] * len(tool_calls)
        with get_executor_for_config(config) as executor:
            outputs = list(
                executor.map(self._run_one, tool_calls, input_types, tool_runtimes)
            )
        return self._combine_tool_outputs(outputs, input_type)

    async def _afunc(
        self,
        input: list[Any] | dict[str, Any] | BaseModel,
        config: RunnableConfig,
        runtime: Runtime,
    ) -> Any:
        tool_calls, input_type = self._parse_input(input)
        config = self._inject_concurrency(config)
        serial = batch_needs_serial(
            list(tool_calls),
            parallel=self._parallel,
            plan_mode=self._plan_mode,
        )
        self.last_mode = "serial" if serial else "parallel"
        tool_runtimes = self._build_runtimes(input, list(tool_calls), config, runtime)

        if serial:
            outputs = []
            for call, tr in zip(tool_calls, tool_runtimes, strict=False):
                outputs.append(await self._arun_one(call, input_type, tr))
            return self._combine_tool_outputs(outputs, input_type)

        if self._max_concurrency is None:
            coros = [
                self._arun_one(call, input_type, tr)
                for call, tr in zip(tool_calls, tool_runtimes, strict=False)
            ]
            outputs = await asyncio.gather(*coros)
            return self._combine_tool_outputs(outputs, input_type)

        sem = asyncio.Semaphore(self._max_concurrency)

        async def _guarded(call: Any, tr: ToolRuntime) -> Any:
            async with sem:
                return await self._arun_one(call, input_type, tr)

        outputs = await asyncio.gather(
            *[
                _guarded(call, tr)
                for call, tr in zip(tool_calls, tool_runtimes, strict=False)
            ]
        )
        return self._combine_tool_outputs(outputs, input_type)


def make_tools_node(
    tools: Any,
    *,
    parallel: bool = True,
    plan_mode: bool = False,
    max_concurrency: int | None = None,
    observation_max_chars: int = 0,
    observation_summarize: bool = False,
    observation_head_ratio: float = 0.6,
    observation_summarizer: Summarizer | None = None,
) -> PolicyToolNode:
    """Factory used by ``build_agent_graph`` (keeps import site tidy)."""
    return PolicyToolNode(
        tools,
        parallel=parallel,
        plan_mode=plan_mode,
        max_concurrency=max_concurrency,
        observation_max_chars=observation_max_chars,
        observation_summarize=observation_summarize,
        observation_head_ratio=observation_head_ratio,
        observation_summarizer=observation_summarizer,
    )
