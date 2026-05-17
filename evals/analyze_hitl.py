"""Honest false-positive measurement: naive flat-threshold flagging vs the
richer HITL escalation policy.

Ground truth: a customer is *genuinely* high-risk iff it is sanctioned or on
a watchlist (the real AML concerns). A false positive = a CLEAN customer that
the policy flags/blocks.

Naive policy   : block whenever rules risk_score >= threshold (flat cutoff).
HITL policy    : escalate (sanctioned OR pep OR HIGH band OR score>=threshold);
                 escalated cases go to a reviewer who clears genuinely-clean
                 customers. So a clean customer is only a residual false
                 positive if the naive cutoff would block it AND the reviewer
                 is modeled as imperfect.

The reviewer is modeled with an explicit, stated accuracy so the number is
not a tautological 100%. We print the measured reduction for the realistic
setting and a sweep, and we do NOT tune the data to hit any target figure.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp_server.schemas import RiskScoreRequest
from mcp_server.tools.risk_scorer import risk_score

_ENTITIES = json.loads(
    (Path(__file__).resolve().parent.parent
     / "mcp_server" / "data" / "entities" / "entities.json").read_text(encoding="utf-8")
)

# Realistic case mix: each entity put through a plausible activity/context.
# Many CLEAN entities are deliberately given risky-looking activity so a flat
# threshold over-flags them — that is exactly the false-positive scenario.
_ACTIVITIES = [
    ("wire_transfer", {"amount": 250_000, "cross_border": True}),
    ("correspondent_banking", {"cross_border": True}),
    ("cash_deposit", {"amount": 15_000}),
    ("securities_trade", {"amount": 5_000}),
    ("account_opening", {}),
]

_THRESHOLD = 0.30  # flat naive cutoff (intentionally aggressive -> over-flags)


def _truly_high_risk(ent: dict) -> bool:
    return bool(ent.get("sanctioned") or ent.get("watchlist"))


def _cases() -> list[dict]:
    cases = []
    for ent in _ENTITIES:
        for act, ctx in _ACTIVITIES:
            r = risk_score(RiskScoreRequest(entity=ent["canonical_name"],
                                            activity=act, context=ctx))
            cases.append({
                "entity": ent["canonical_name"],
                "clean": not _truly_high_risk(ent),
                "score": r.score,
                "band": r.band,
                "sanctioned": r.sanctioned,
                "pep": r.pep,
            })
    return cases


def measure(reviewer_accuracy: float) -> dict:
    cases = _cases()

    # Naive: block if score >= threshold. FP = blocked & clean.
    naive_fp = sum(1 for c in cases if c["score"] >= _THRESHOLD and c["clean"])

    # HITL: flagged cases are escalated, not auto-blocked. A modeled reviewer
    # correctly clears a clean customer with probability `reviewer_accuracy`;
    # otherwise the false positive survives. Deterministic expectation.
    flagged_clean = [
        c for c in cases
        if (c["score"] >= _THRESHOLD or c["sanctioned"] or c["pep"]
            or c["band"] == "high") and c["clean"]
    ]
    hitl_fp = round(len(flagged_clean) * (1.0 - reviewer_accuracy))

    reduction = 0.0 if naive_fp == 0 else (naive_fp - hitl_fp) / naive_fp
    return {
        "n_cases": len(cases),
        "naive_false_positives": naive_fp,
        "hitl_false_positives": hitl_fp,
        "reviewer_accuracy": reviewer_accuracy,
        "fp_reduction_pct": round(reduction * 100, 1),
    }


if __name__ == "__main__":
    print(f"cases evaluated, flat threshold = {_THRESHOLD}\n")
    print(" reviewer_acc | naive_FP | hitl_FP | FP reduction")
    print(" -------------|----------|---------|-------------")
    for acc in (0.80, 0.85, 0.90, 0.95, 1.00):
        m = measure(acc)
        print(f"     {acc:0.2f}    |   {m['naive_false_positives']:3}    |"
              f"   {m['hitl_false_positives']:3}   |   {m['fp_reduction_pct']:5}%")
    print("\nNote: the reduction is a function of the modeled reviewer "
          "accuracy and the case mix. It is reported across a sweep, not "
          "cherry-picked. Do not state a single figure without its "
          "reviewer-accuracy assumption.")
