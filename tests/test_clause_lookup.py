"""Clause lookup retrieval relevance over the BSA/CIP corpus."""
from __future__ import annotations

import pytest

from mcp_server.schemas import ClauseLookupRequest
from mcp_server.tools.clause_lookup import clause_lookup


def _lookup(q: str, top_k: int = 3, jurisdiction: str | None = None):
    return clause_lookup(
        ClauseLookupRequest(query=q, top_k=top_k, jurisdiction=jurisdiction)
    )


@pytest.mark.parametrize(
    "query,expected_citation",
    [
        ("When must a bank file a CTR for cash deposits?", "31 CFR 1010.311"),
        ("What identity info is required to open an account?", "31 CFR 1020.220(a)(2)"),
        ("When do we file a suspicious activity report?", "31 CFR 1020.320"),
        ("rules about correspondent accounts for foreign shell banks", "31 CFR 1010.605"),
    ],
)
def test_relevant_clause_in_top_results(query: str, expected_citation: str) -> None:
    resp = _lookup(query, top_k=3)
    citations = [c.citation for c in resp.clauses]
    assert expected_citation in citations, f"{expected_citation} not in {citations}"


def test_respects_top_k() -> None:
    resp = _lookup("anti money laundering program", top_k=2)
    assert len(resp.clauses) <= 2


def test_scores_descending_and_bounded() -> None:
    resp = _lookup("beneficial ownership of legal entity customers", top_k=5)
    scores = [c.score for c in resp.clauses]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_jurisdiction_filter() -> None:
    resp = _lookup("sanctions blocking obligations", top_k=5, jurisdiction="US-OFAC")
    assert resp.clauses
    assert resp.clauses[0].citation == "OFAC 31 CFR 501.603"
