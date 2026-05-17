"""Short-term memory: per-conversation state via a LangGraph checkpointer.

Each session_id maps to a checkpointer thread, so successive turns in the same
conversation see prior messages without the caller replaying history.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver


@lru_cache(maxsize=1)
def get_checkpointer() -> InMemorySaver:
    """Process-wide saver shared across agent invocations."""
    return InMemorySaver()


class SessionMemory:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    @property
    def config(self) -> dict:
        """Pass as the `config` arg to agent.ainvoke to bind this thread."""
        return {"configurable": {"thread_id": self.session_id}}
