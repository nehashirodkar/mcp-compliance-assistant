"""HITL webhook + escalation policy + audit trail."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HITL_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from hitl import audit
    from hitl.webhook import _CASES, app

    _CASES.clear()
    return TestClient(app), audit


def _req(**kw):
    base = {
        "entity": "Northwind Trading LLC",
        "activity": "securities_trade",
        "risk_score": 0.1,
        "band": "low",
    }
    base.update(kw)
    return base


def test_health(client):
    c, _ = client
    assert c.get("/health").json() == {"status": "ok"}


def test_low_risk_auto_cleared(client):
    c, audit = client
    r = c.post("/escalate", json=_req()).json()
    assert r["escalated"] is False
    assert r["status"] == "auto_cleared"
    assert [e["event"] for e in audit.read_all()] == ["auto_cleared"]


def test_sanctioned_always_escalates(client):
    c, audit = client
    r = c.post(
        "/escalate",
        json=_req(entity="Volkov Petrochemical OAO", risk_score=1.0,
                  band="high", sanctioned=True),
    ).json()
    assert r["escalated"] is True
    assert r["case_id"].startswith("CASE-")
    assert any("sanctioned" in x for x in r["reasons"])
    assert audit.read_all()[0]["event"] == "escalated"


def test_review_flow_and_audit(client):
    c, audit = client
    case_id = c.post(
        "/escalate", json=_req(risk_score=0.9, band="high")
    ).json()["case_id"]

    pending = c.get("/cases", params={"status": "pending_review"}).json()
    assert len(pending) == 1

    out = c.post(
        f"/cases/{case_id}/review",
        json={"decision": "rejected", "reviewer": "analyst@bank", "note": "false positive"},
    ).json()
    assert out["status"] == "rejected"
    assert out["reviewer"] == "analyst@bank"

    events = [e["event"] for e in audit.read_all()]
    assert events == ["escalated", "reviewed"]


def test_double_review_conflicts(client):
    c, _ = client
    cid = c.post("/escalate", json=_req(risk_score=0.9, band="high")).json()["case_id"]
    c.post(f"/cases/{cid}/review", json={"decision": "approved", "reviewer": "a"})
    r2 = c.post(f"/cases/{cid}/review", json={"decision": "approved", "reviewer": "a"})
    assert r2.status_code == 409


def test_review_missing_case_404(client):
    c, _ = client
    r = c.post("/cases/CASE-nope/review", json={"decision": "approved", "reviewer": "a"})
    assert r.status_code == 404
