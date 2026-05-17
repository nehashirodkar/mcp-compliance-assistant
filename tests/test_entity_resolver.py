"""Entity resolver behavior over the seed AML/KYC table."""
from __future__ import annotations

from mcp_server.schemas import EntityResolveRequest
from mcp_server.tools.entity_resolver import entity_resolve


def _resolve(name: str):
    return entity_resolve(EntityResolveRequest(name=name))


def test_exact_canonical_match() -> None:
    r = _resolve("Northwind Trading LLC")
    assert r.matched is True
    assert r.entity_id == "ENT-1001"
    assert r.confidence >= 0.99
    assert r.sanctioned is False


def test_alias_match_resolves_to_canonical() -> None:
    r = _resolve("NW Trading LLC")
    assert r.matched is True
    assert r.canonical_name == "Northwind Trading LLC"


def test_typo_still_matches() -> None:
    r = _resolve("Helios Captial Partnrs")
    assert r.matched is True
    assert r.entity_id == "ENT-1002"


def test_sanctioned_flags_surface() -> None:
    r = _resolve("Volkov Petrochem")
    assert r.matched is True
    assert r.sanctioned is True
    assert r.watchlist is True


def test_pep_flag_surfaces() -> None:
    r = _resolve("Dmitry Sokolov")
    assert r.matched is True
    assert r.pep is True


def test_unknown_name_does_not_false_match() -> None:
    r = _resolve("Acme Widgets International Group")
    assert r.matched is False
    assert r.entity_id is None
