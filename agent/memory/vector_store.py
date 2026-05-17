"""Long-term memory: Chroma-backed store for multi-document context.

Lets a conversation that spans 20+ pages stay within the context window —
large text is chunked on write and only the relevant chunks are recalled per
query instead of replaying everything into the prompt.
"""
from __future__ import annotations

import uuid

import chromadb

from config.settings import get_settings

_COLLECTION = "agent_memory"


def _chunk(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    step = size - overlap
    return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]


class VectorMemory:
    def __init__(self, persist_dir: str | None = None) -> None:
        self.persist_dir = persist_dir or get_settings().chroma_persist_dir
        client = chromadb.PersistentClient(path=self.persist_dir)
        self._col = client.get_or_create_collection(
            name=_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def add(self, text: str, session_id: str, source: str = "conversation") -> int:
        chunks = _chunk(text)
        if not chunks:
            return 0
        base = uuid.uuid4().hex
        self._col.add(
            ids=[f"{base}-{i}" for i in range(len(chunks))],
            documents=chunks,
            metadatas=[
                {"session_id": session_id, "source": source, "chunk": i}
                for i in range(len(chunks))
            ],
        )
        return len(chunks)

    def recall(self, query: str, session_id: str, k: int = 4) -> list[str]:
        if self._col.count() == 0:
            return []
        res = self._col.query(
            query_texts=[query],
            n_results=k,
            where={"session_id": session_id},
        )
        return res.get("documents", [[]])[0]
