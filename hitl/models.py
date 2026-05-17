"""Pydantic models for the HITL escalation layer."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EscalationRequest(BaseModel):
    """What the agent sends when a decision may need a human."""

    entity: str
    activity: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    band: str
    sanctioned: bool = False
    pep: bool = False
    watchlist: bool = False
    factors: list[str] = Field(default_factory=list)
    agent_recommendation: str = ""


class EscalationDecision(BaseModel):
    escalate: bool
    reasons: list[str] = Field(default_factory=list)


class Case(BaseModel):
    case_id: str
    status: str = "pending_review"  # pending_review | approved | rejected
    created_at: str = Field(default_factory=_now)
    reviewed_at: str | None = None
    reviewer: str | None = None
    review_note: str | None = None
    request: EscalationRequest
