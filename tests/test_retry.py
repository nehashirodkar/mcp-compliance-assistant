"""Retry guard: tool failures must never escape into the agent loop."""
from __future__ import annotations

from langchain_core.tools import StructuredTool

from agent.retry import safe_tool_call, wrap_tool


def _tool(fn, name="t"):
    return StructuredTool.from_function(fn, name=name, description=name)


async def test_always_failing_tool_returns_error_string() -> None:
    def boom(x: int) -> str:
        raise RuntimeError("kaboom")

    wrapped = wrap_tool(_tool(boom), max_retries=2)
    out = await wrapped.ainvoke({"x": 1})
    assert isinstance(out, str)
    assert out.startswith("[tool_error]")
    assert "kaboom" in out


async def test_empty_response_treated_as_failure() -> None:
    wrapped = wrap_tool(_tool(lambda x: "   ", name="blank"), max_retries=1)
    out = await wrapped.ainvoke({"x": 1})
    assert out.startswith("[tool_error]")


async def test_recovers_within_retry_budget() -> None:
    calls = {"n": 0}

    def flaky(x: int) -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    wrapped = wrap_tool(_tool(flaky), max_retries=2)
    out = await wrapped.ainvoke({"x": 1})
    assert out == "ok"
    assert calls["n"] == 3


async def test_success_passes_through() -> None:
    wrapped = wrap_tool(_tool(lambda x: f"got {x}", name="ok"), max_retries=2)
    assert await wrapped.ainvoke({"x": 5}) == "got 5"


def test_safe_tool_call_sync_recovery() -> None:
    def bad():
        raise KeyError("nope")

    r = safe_tool_call(bad, max_retries=1)
    assert r["recovered"] is True
    assert "KeyError" in r["error"]
    assert safe_tool_call(lambda a, b: a + b, 2, 3) == 5
