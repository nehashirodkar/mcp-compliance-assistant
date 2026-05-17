"""Regulatory clause lookup — RAG over the BSA/CIP corpus."""
from __future__ import annotations

from mcp_server.clause_index import query_clauses
from mcp_server.schemas import Clause, ClauseLookupRequest, ClauseLookupResponse


def clause_lookup(req: ClauseLookupRequest) -> ClauseLookupResponse:
    hits = query_clauses(
        query=req.query, top_k=req.top_k, jurisdiction=req.jurisdiction
    )
    return ClauseLookupResponse(clauses=[Clause(**h) for h in hits])
