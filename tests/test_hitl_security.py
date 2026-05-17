"""Phase 8 hardening: API-key auth, rate limiting, request-id logging."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HITL_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    from hitl.security import reset_rate_limit
    from hitl.webhook import _CASES, app

    _CASES.clear()
    reset_rate_limit()
    return TestClient(app, raise_server_exceptions=False), monkeypatch


_ESC = {
    "entity": "Volkov Petrochemical OAO",
    "activity": "wire_transfer",
    "risk_score": 1.0,
    "band": "high",
    "sanctioned": True,
}


def test_health_open_no_key_required(client):
    c, _ = client
    assert c.get("/health").status_code == 200


def test_auth_disabled_when_no_key_configured(client):
    c, _ = client  # no HITL_API_KEY set -> fail-open dev mode
    assert c.post("/escalate", json=_ESC).status_code == 200


def test_rejects_missing_and_wrong_key(client):
    c, mp = client
    mp.setenv("HITL_API_KEY", "secret-123")
    assert c.post("/escalate", json=_ESC).status_code == 401
    assert c.post("/escalate", json=_ESC, headers={"X-API-Key": "nope"}).status_code == 401


def test_accepts_correct_key(client):
    c, mp = client
    mp.setenv("HITL_API_KEY", "secret-123")
    r = c.post("/escalate", json=_ESC, headers={"X-API-Key": "secret-123"})
    assert r.status_code == 200
    assert r.json()["escalated"] is True


def test_rate_limit_returns_429(client):
    c, mp = client
    mp.setenv("RATE_LIMIT_MAX", "3")
    mp.setenv("RATE_LIMIT_WINDOW_S", "60")
    codes = [c.get("/cases").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429 and codes[4] == 429


def test_request_id_header_present(client):
    c, _ = client
    r = c.get("/health")
    assert len(r.headers.get("X-Request-ID", "")) >= 8


def test_request_id_is_propagated(client):
    c, _ = client
    r = c.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["X-Request-ID"] == "trace-abc-123"
