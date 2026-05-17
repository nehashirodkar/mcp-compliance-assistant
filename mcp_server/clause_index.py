"""Chroma-backed index over the BSA/CIP corpus.

Uses Chroma's default local embedding model (ONNX MiniLM) — no API key, no
per-query embedding cost, which keeps clause lookup off the token budget.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import chromadb

from config.settings import get_settings

_CORPUS_PATH = Path(__file__).resolve().parent / "data" / "regulations" / "bsa_cip.json"
_COLLECTION = "bsa_clauses"


def _load_corpus() -> list[dict]:
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_collection():
    client = chromadb.PersistentClient(path=get_settings().chroma_persist_dir)
    col = client.get_or_create_collection(
        name=_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    corpus = _load_corpus()
    if col.count() < len(corpus):
        col.upsert(
            ids=[c["citation"] for c in corpus],
            documents=[f"{c['title']}. {c['text']}" for c in corpus],
            metadatas=[
                {
                    "citation": c["citation"],
                    "title": c["title"],
                    "jurisdiction": c["jurisdiction"],
                    "text": c["text"],
                }
                for c in corpus
            ],
        )
    return col


def query_clauses(
    query: str, top_k: int = 5, jurisdiction: str | None = None
) -> list[dict]:
    col = get_collection()
    where = {"jurisdiction": jurisdiction} if jurisdiction else None
    res = col.query(query_texts=[query], n_results=top_k, where=where)

    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    out: list[dict] = []
    for meta, dist in zip(metas, dists):
        out.append(
            {
                "citation": meta["citation"],
                "text": meta["text"],
                # cosine distance -> similarity in [0, 1]
                "score": round(max(0.0, 1.0 - float(dist)), 4),
            }
        )
    return out
