"""Decides when an agent decision must go to a human reviewer.

Beyond a flat threshold: sanctions/PEP hits always escalate (regulated-industry
requirement), as do HIGH-band decisions, regardless of the numeric score.
"""
from __future__ import annotations

from hitl.models import EscalationDecision, EscalationRequest


def evaluate(req: EscalationRequest, threshold: float) -> EscalationDecision:
    reasons: list[str] = []

    if req.sanctioned:
        reasons.append("entity is sanctioned — mandatory human review")
    if req.pep:
        reasons.append("politically exposed person")
    if req.band.lower() == "high":
        reasons.append("risk band is HIGH")
    if req.risk_score >= threshold:
        reasons.append(f"risk score {req.risk_score:.2f} >= threshold {threshold:.2f}")

    return EscalationDecision(escalate=bool(reasons), reasons=reasons)


def should_escalate(risk_score: float, threshold: float) -> bool:
    """Back-compat thin helper."""
    return risk_score >= threshold
