"""Defensive retry layer — keeps the agent loop alive on malformed tool output.

A raised exception or empty/None result from a tool would otherwise abort the
ReAct loop. Instead we bound-retry, and on final failure return a structured
error *string* the model can read and recover from (re-plan, ask the user, or
proceed without that tool's output).
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool


def _is_empty(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, str) and not result.strip():
        return True
    return False


async def _guarded_ainvoke(tool: BaseTool, max_retries: int, kwargs: dict) -> Any:
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            result = await tool.ainvoke(kwargs)
            if _is_empty(result):
                raise ValueError("empty tool response")
            return result
        except Exception as e:  # noqa: BLE001 — deliberately broad: never escape
            last_err = e
    return (
        f"[tool_error] '{tool.name}' failed after {max_retries + 1} attempt(s): "
        f"{type(last_err).__name__}: {last_err}. Do not retry it again — either "
        f"answer using other tools/known information, or tell the user what you "
        f"could not verify."
    )


def wrap_tool(tool: BaseTool, max_retries: int = 2) -> StructuredTool:
    """Return a drop-in tool that never raises into the agent loop."""

    async def _coro(**kwargs: Any) -> Any:
        return await _guarded_ainvoke(tool, max_retries, kwargs)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=_coro,
    )


def wrap_tools(tools: list[BaseTool], max_retries: int = 2) -> list[StructuredTool]:
    return [wrap_tool(t, max_retries) for t in tools]


def safe_tool_call(
    fn: Callable[..., Any], *args: Any, max_retries: int = 2, **kwargs: Any
) -> Any:
    """Generic guard for a plain (sync or async) callable."""
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = asyncio.get_event_loop().run_until_complete(result)
            if _is_empty(result):
                raise ValueError("empty response")
            return result
        except Exception as e:  # noqa: BLE001
            last_err = e
    return {"error": f"{type(last_err).__name__}: {last_err}", "recovered": True}
