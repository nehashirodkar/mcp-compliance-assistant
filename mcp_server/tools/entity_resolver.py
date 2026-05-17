"""Entity resolver — fuzzy match a raw name to a canonical AML/KYC entity."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from mcp_server.schemas import EntityResolveRequest, EntityResolveResponse

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "entities" / "entities.json"

# Below this score, we treat it as no confident match (avoids false KYC hits).
_MATCH_THRESHOLD = 75.0


@lru_cache(maxsize=1)
def _load_entities() -> list[dict]:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[str, int]]:
    """Flatten (canonical + every alias) -> index into the entity list."""
    pairs: list[tuple[str, int]] = []
    for i, ent in enumerate(_load_entities()):
        pairs.append((ent["canonical_name"], i))
        for alias in ent.get("aliases", []):
            pairs.append((alias, i))
    return pairs


def entity_resolve(req: EntityResolveRequest) -> EntityResolveResponse:
    # Defensive: an empty or too-short name must never fuzzy-match a real
    # (possibly sanctioned) entity — that would be a false KYC/sanctions hit.
    name = (req.name or "").strip()
    if len(name) < 3:
        return EntityResolveResponse(
            canonical_name=req.name, entity_id=None, confidence=0.0, matched=False
        )

    entities = _load_entities()
    index = _alias_index()
    choices = [name for name, _ in index]

    results = process.extract(
        req.name, choices, scorer=fuzz.WRatio, limit=5
    )
    if not results:
        return EntityResolveResponse(
            canonical_name=req.name, entity_id=None, confidence=0.0, matched=False
        )

    best_name, best_score, best_pos = results[0]
    ent = entities[index[best_pos][1]]

    # Distinct canonical names from the remaining candidates, in score order.
    seen = {ent["canonical_name"]}
    candidates: list[str] = []
    for name, _score, pos in results[1:]:
        cn = entities[index[pos][1]]["canonical_name"]
        if cn not in seen:
            seen.add(cn)
            candidates.append(cn)

    if best_score < _MATCH_THRESHOLD:
        return EntityResolveResponse(
            canonical_name=req.name,
            entity_id=None,
            confidence=round(best_score / 100.0, 4),
            matched=False,
            candidates=[ent["canonical_name"], *candidates],
        )

    return EntityResolveResponse(
        canonical_name=ent["canonical_name"],
        entity_id=ent["entity_id"],
        confidence=round(best_score / 100.0, 4),
        matched=True,
        type=ent.get("type"),
        jurisdiction=ent.get("jurisdiction"),
        sanctioned=ent.get("sanctioned", False),
        pep=ent.get("pep", False),
        watchlist=ent.get("watchlist", False),
        candidates=candidates,
    )
