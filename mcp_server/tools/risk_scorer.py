"""Risk scorer — rules-only AML/KYC customer risk rating.

Deterministic and explainable: every contributing rule appends a human-readable
factor. The LLM layer for ambiguous cases is deferred to Phase 6, so this stays
the measured baseline for the false-positive comparison.
"""
from __future__ import annotations

from mcp_server.schemas import EntityResolveRequest, RiskScoreRequest, RiskScoreResponse
from mcp_server.tools.entity_resolver import entity_resolve

# FATF-style higher-risk jurisdictions (illustrative seed set).
_HIGH_RISK_JURISDICTIONS = {"IR", "KP", "RU", "SY", "MM"}
_ELEVATED_JURISDICTIONS = {"PA", "NG", "KY", "VG"}

# Inherent AML risk weight per activity type.
_ACTIVITY_RISK = {
    "correspondent_banking": 0.35,
    "crypto_exchange": 0.30,
    "wire_transfer": 0.20,
    "trade_finance": 0.20,
    "cash_deposit": 0.25,
    "account_opening": 0.10,
    "securities_trade": 0.10,
}

_LARGE_AMOUNT = 10_000.0  # USD; mirrors CTR reporting salience


def _band(score: float) -> str:
    if score >= 0.70:
        return "high"
    if score >= 0.30:
        return "medium"
    return "low"


def risk_score(req: RiskScoreRequest) -> RiskScoreResponse:
    score = 0.0
    factors: list[str] = []

    resolved = entity_resolve(EntityResolveRequest(name=req.entity))

    if resolved.matched and resolved.sanctioned:
        score = 1.0
        factors.append(
            f"Entity '{resolved.canonical_name}' is on a sanctions list (auto high-risk)"
        )
    else:
        if resolved.matched and resolved.pep:
            score += 0.35
            factors.append(f"Entity '{resolved.canonical_name}' is a politically exposed person")
        if resolved.matched and resolved.watchlist:
            score += 0.20
            factors.append(f"Entity '{resolved.canonical_name}' appears on an internal watchlist")
        if not resolved.matched:
            score += 0.15
            factors.append("Entity could not be resolved to a known record (KYC gap)")

        jurisdiction = req.context.get("jurisdiction") or resolved.jurisdiction
        if jurisdiction in _HIGH_RISK_JURISDICTIONS:
            score += 0.30
            factors.append(f"Counterparty jurisdiction '{jurisdiction}' is high-risk (FATF)")
        elif jurisdiction in _ELEVATED_JURISDICTIONS:
            score += 0.15
            factors.append(f"Counterparty jurisdiction '{jurisdiction}' is elevated-risk")

        activity = (req.activity or "").strip().lower()
        if activity in _ACTIVITY_RISK:
            w = _ACTIVITY_RISK[activity]
            score += w
            factors.append(f"Activity '{activity}' carries inherent AML risk (+{w:.2f})")
        else:
            factors.append(f"Activity '{activity}' has no specific risk weighting")

        amount = req.context.get("amount")
        if isinstance(amount, (int, float)) and amount >= _LARGE_AMOUNT:
            score += 0.10
            factors.append(f"Transaction amount ${amount:,.0f} at or above reporting salience")

        if req.context.get("cross_border") is True:
            score += 0.10
            factors.append("Cross-border transaction")

    score = round(min(score, 1.0), 4)
    return RiskScoreResponse(
        score=score,
        band=_band(score),
        factors=factors,
        resolved_entity=resolved.canonical_name if resolved.matched else None,
        entity_matched=resolved.matched,
        sanctioned=resolved.sanctioned,
        pep=resolved.pep,
        watchlist=resolved.watchlist,
    )
