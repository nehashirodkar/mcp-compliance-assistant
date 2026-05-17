"""MCP server entry point. Registers the 3 compliance tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_server.schemas import (
    ClauseLookupRequest,
    EntityResolveRequest,
    RiskScoreRequest,
)
from mcp_server.tools.clause_lookup import clause_lookup
from mcp_server.tools.entity_resolver import entity_resolve
from mcp_server.tools.risk_scorer import risk_score

mcp = FastMCP("compliance-assistant")


@mcp.tool()
def regulatory_clause_lookup(query: str, top_k: int = 3) -> dict:
    """Look up regulatory clauses relevant to a compliance question.

    Pass a natural-language description of the issue. Returns the most
    relevant clauses with their exact citations and similarity scores.
    """
    return clause_lookup(
        ClauseLookupRequest(query=query, jurisdiction=None, top_k=top_k)
    ).model_dump()


@mcp.tool()
def compliance_risk_score(entity: str, activity: str, context: dict | None = None) -> dict:
    """Score the compliance risk of an entity performing an activity."""
    return risk_score(
        RiskScoreRequest(entity=entity, activity=activity, context=context or {})
    ).model_dump()


@mcp.tool()
def resolve_entity(name: str, hint: str | None = None) -> dict:
    """Resolve a raw entity name to its canonical form."""
    return entity_resolve(EntityResolveRequest(name=name, hint=hint)).model_dump()


if __name__ == "__main__":
    mcp.run()
