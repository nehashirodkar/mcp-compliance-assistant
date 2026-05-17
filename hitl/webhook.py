"""FastAPI webhook: routes high-risk decisions to human reviewers.

Every escalation and every review outcome is written to the append-only
audit trail before the response is returned.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from config.settings import get_settings
from hitl import audit
from hitl.escalation_policy import evaluate
from hitl.models import Case, EscalationRequest, _now
from hitl.security import RequestContextMiddleware, rate_limit, require_api_key

app = FastAPI(title="compliance-hitl")
app.add_middleware(RequestContextMiddleware)

# Auth + rate limit on every data/mutation route; /health stays open.
_guard = [Depends(require_api_key), Depends(rate_limit)]

# In-memory case store; the durable record is the audit log.
_CASES: dict[str, Case] = {}


class ReviewInput(BaseModel):
    decision: str  # approved | rejected
    reviewer: str
    note: str = ""


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/escalate", dependencies=_guard)
async def escalate(req: EscalationRequest) -> dict:
    threshold = get_settings().hitl_risk_threshold
    decision = evaluate(req, threshold)

    if not decision.escalate:
        audit.record("auto_cleared", {"request": req.model_dump(), "threshold": threshold})
        return {"escalated": False, "reasons": [], "status": "auto_cleared"}

    case = Case(case_id=f"CASE-{uuid.uuid4().hex[:10]}", request=req)
    _CASES[case.case_id] = case
    audit.record(
        "escalated",
        {"case_id": case.case_id, "reasons": decision.reasons, "request": req.model_dump()},
    )
    return {
        "escalated": True,
        "case_id": case.case_id,
        "status": case.status,
        "reasons": decision.reasons,
    }


@app.get("/cases", dependencies=_guard)
async def list_cases(status: str | None = None) -> list[dict]:
    cases = list(_CASES.values())
    if status:
        cases = [c for c in cases if c.status == status]
    return [c.model_dump() for c in cases]


@app.get("/cases/{case_id}", dependencies=_guard)
async def get_case(case_id: str) -> dict:
    case = _CASES.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case.model_dump()


@app.post("/cases/{case_id}/review", dependencies=_guard)
async def review(case_id: str, body: ReviewInput) -> dict:
    case = _CASES.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    if body.decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="decision must be approved|rejected")
    if case.status != "pending_review":
        raise HTTPException(status_code=409, detail=f"case already {case.status}")

    case.status = body.decision
    case.reviewer = body.reviewer
    case.review_note = body.note
    case.reviewed_at = _now()
    audit.record(
        "reviewed",
        {
            "case_id": case_id,
            "decision": body.decision,
            "reviewer": body.reviewer,
            "note": body.note,
        },
    )
    return case.model_dump()
