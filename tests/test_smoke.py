"""Smoke test: scaffold imports cleanly."""
from __future__ import annotations


def test_imports() -> None:
    import agent.graph  # noqa: F401
    import hitl.escalation_policy  # noqa: F401
    import mcp_server.schemas  # noqa: F401


def test_escalation_threshold() -> None:
    from hitl.escalation_policy import should_escalate

    assert should_escalate(0.9, 0.75) is True
    assert should_escalate(0.5, 0.75) is False
