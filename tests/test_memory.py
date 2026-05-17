"""Session config + long-term vector memory behavior."""
from __future__ import annotations

from agent.memory.session import SessionMemory, get_checkpointer
from agent.memory.vector_store import VectorMemory


def test_session_config_binds_thread() -> None:
    assert SessionMemory("abc").config == {"configurable": {"thread_id": "abc"}}


def test_checkpointer_is_process_singleton() -> None:
    assert get_checkpointer() is get_checkpointer()


def test_long_document_is_chunked(tmp_path) -> None:
    vm = VectorMemory(persist_dir=str(tmp_path / "chroma"))
    long_doc = ("Customer due diligence requires ongoing monitoring. " * 200)
    n = vm.add(long_doc, session_id="s1", source="doc")
    assert n > 1


def test_recall_is_session_scoped(tmp_path) -> None:
    vm = VectorMemory(persist_dir=str(tmp_path / "chroma"))
    vm.add(
        "The customer is Volkov Petrochemical, flagged on the sanctions list.",
        session_id="s1",
    )
    vm.add(
        "The customer is Northwind Trading, a low-risk domestic entity.",
        session_id="s2",
    )

    s1 = " ".join(vm.recall("who is the customer?", session_id="s1"))
    s2 = " ".join(vm.recall("who is the customer?", session_id="s2"))

    assert "Volkov" in s1 and "Volkov" not in s2
    assert "Northwind" in s2


def test_recall_empty_store_returns_empty(tmp_path) -> None:
    vm = VectorMemory(persist_dir=str(tmp_path / "chroma"))
    assert vm.recall("anything", session_id="none") == []
