"""Pydantic I/O models for the MCP tools. One request/response pair per tool."""
from __future__ import annotations

from pydantic import BaseModel, Field


# --- clause_lookup ---
class ClauseLookupRequest(BaseModel):
    query: str = Field(..., description="Natural-language compliance question")
    jurisdiction: str | None = Field(None, description="e.g. 'US-SEC', 'EU-MiFID'")
    top_k: int = Field(3, ge=1, le=20)


class Clause(BaseModel):
    citation: str
    text: str
    score: float


class ClauseLookupResponse(BaseModel):
    clauses: list[Clause]


# --- risk_scorer ---
class RiskScoreRequest(BaseModel):
    entity: str
    activity: str
    context: dict = Field(default_factory=dict)


class RiskScoreResponse(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    band: str  # low | medium | high
    factors: list[str]
    resolved_entity: str | None = None
    entity_matched: bool = False
    sanctioned: bool = False
    pep: bool = False
    watchlist: bool = False


# --- entity_resolver ---
class EntityResolveRequest(BaseModel):
    name: str
    hint: str | None = None


class EntityResolveResponse(BaseModel):
    canonical_name: str
    entity_id: str | None
    confidence: float
    matched: bool
    type: str | None = None
    jurisdiction: str | None = None
    sanctioned: bool = False
    pep: bool = False
    watchlist: bool = False
    candidates: list[str] = Field(default_factory=list)
