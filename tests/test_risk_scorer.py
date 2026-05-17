"""Risk scorer rule behavior."""
from __future__ import annotations

from mcp_server.schemas import RiskScoreRequest
from mcp_server.tools.risk_scorer import risk_score


def _score(entity: str, activity: str, **context):
    return risk_score(RiskScoreRequest(entity=entity, activity=activity, context=context))


def test_sanctioned_entity_forces_high() -> None:
    r = _score("Volkov Petrochem", "wire_transfer")
    assert r.score == 1.0
    assert r.band == "high"
    assert any("sanctions" in f for f in r.factors)


def test_clean_domestic_low_risk() -> None:
    r = _score("Northwind Trading LLC", "securities_trade")
    assert r.band == "low"
    assert r.score < 0.30


def test_pep_plus_activity_is_medium() -> None:
    r = _score("Amara Okonkwo", "wire_transfer")
    assert r.band in {"medium", "high"}
    assert any("politically exposed" in f for f in r.factors)


def test_unresolved_entity_flags_kyc_gap() -> None:
    r = _score("Totally Unknown Shell Co", "cash_deposit")
    assert any("KYC gap" in f for f in r.factors)


def test_high_risk_jurisdiction_override_via_context() -> None:
    r = _score("Northwind Trading LLC", "wire_transfer", jurisdiction="IR")
    assert any("high-risk" in f for f in r.factors)
    assert r.score >= 0.30


def test_large_cross_border_amount_adds_risk() -> None:
    base = _score("Northwind Trading LLC", "wire_transfer")
    loaded = _score(
        "Northwind Trading LLC", "wire_transfer", amount=250000, cross_border=True
    )
    assert loaded.score > base.score
    assert any("Cross-border" in f for f in loaded.factors)


def test_score_never_exceeds_one() -> None:
    r = _score(
        "Dmitri A. Sokolov",
        "correspondent_banking",
        jurisdiction="KP",
        amount=5_000_000,
        cross_border=True,
    )
    assert r.score <= 1.0
