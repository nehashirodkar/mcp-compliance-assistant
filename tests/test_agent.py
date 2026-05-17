"""Agent wiring: MCP tools load over stdio; live query gated on an API key."""
from __future__ import annotations

import uuid

import pytest

from agent.graph import ask, list_mcp_tools
from config.settings import get_settings

_needs_key = pytest.mark.skipif(
    not get_settings().anthropic_api_key,
    reason="no ANTHROPIC_API_KEY in env/.env — skipping live LLM call",
)


async def test_mcp_tools_load_over_stdio() -> None:
    names = await list_mcp_tools()
    assert set(names) == {
        "regulatory_clause_lookup",
        "compliance_risk_score",
        "resolve_entity",
    }


@_needs_key
async def test_live_compliance_query() -> None:
    answer = await ask(
        "A new legal-entity customer wants to open an account. What identity "
        "and beneficial-ownership info must we collect? Cite the rule."
    )
    assert isinstance(answer, str) and answer
    assert "1010.230" in answer or "1020.220" in answer


@_needs_key
async def test_live_session_memory_carries_context() -> None:
    sid = f"test-{uuid.uuid4().hex[:8]}"
    await ask(
        "Assess onboarding risk for the customer 'Volkov Petrochem'.",
        session_id=sid,
    )
    follow_up = await ask(
        "Without me repeating the name — is that same customer sanctioned?",
        session_id=sid,
    )
    assert "volkov" in follow_up.lower() or "sanction" in follow_up.lower()
