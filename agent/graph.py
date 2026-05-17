"""LangGraph agent: connects to the MCP server over stdio, orchestrates the
compliance tools, and answers with citations.

Phase 4 adds: retry-guarded tools, per-session checkpointer memory, and
long-term Chroma recall so long conversations stay within context.
"""
from __future__ import annotations

import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.memory.session import SessionMemory, get_checkpointer
from agent.memory.vector_store import VectorMemory
from agent.retry import wrap_tools
from config.settings import get_settings

_ROOT = Path(__file__).resolve().parent.parent
_PROMPT_PATH = _ROOT / "agent" / "prompts" / "system.txt"


def _mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "compliance": {
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "transport": "stdio",
                "cwd": str(_ROOT),
            }
        }
    )


def _system_message() -> SystemMessage:
    text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return SystemMessage(
        content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    )


async def build_agent():
    settings = get_settings()
    tools = wrap_tools(await _mcp_client().get_tools(), max_retries=2)
    model = ChatAnthropic(
        model=settings.agent_model,
        temperature=0,
        max_tokens=1024,
        anthropic_api_key=settings.anthropic_api_key,
    )
    return create_agent(
        model,
        tools,
        system_prompt=_system_message(),
        checkpointer=get_checkpointer(),
    )


def remember(text: str, session_id: str = "default", source: str = "document") -> int:
    """Ingest a large document into long-term memory for later recall."""
    return VectorMemory().add(text, session_id=session_id, source=source)


async def ask(question: str, session_id: str = "default", recall: bool = True) -> str:
    session = SessionMemory(session_id)
    agent = await build_agent()

    content = question
    if recall:
        snippets = VectorMemory().recall(question, session_id=session_id, k=4)
        if snippets:
            ctx = "\n\n".join(f"- {s}" for s in snippets)
            content = (
                f"Relevant context from earlier in this matter:\n{ctx}\n\n"
                f"Question: {question}"
            )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=content)]}, config=session.config
    )
    return result["messages"][-1].content


async def answer_with_trace(question: str, session_id: str | None = None) -> dict:
    """Run the agent and return the answer plus a structured tool trace and
    any HITL escalation — used by the demo UI. Each call gets an isolated
    session by default so stateless demo queries never bleed context."""
    import uuid

    from langchain_core.messages import AIMessage, ToolMessage

    session = SessionMemory(session_id or f"demo-{uuid.uuid4().hex[:8]}")
    agent = await build_agent()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=question)]}, config=session.config
    )
    messages = result["messages"]

    # Map tool_call_id -> result content.
    results: dict[str, str] = {}
    for m in messages:
        if isinstance(m, ToolMessage):
            results[m.tool_call_id] = m.content

    steps: list[dict] = []
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls or []:
                steps.append(
                    {
                        "tool": tc["name"],
                        "args": tc.get("args", {}),
                        "result": results.get(tc["id"], ""),
                    }
                )

    answer = messages[-1].content
    if isinstance(answer, list):
        answer = " ".join(b.get("text", "") for b in answer if isinstance(b, dict))

    escalation = _maybe_escalate(question, steps)
    return {"answer": answer, "steps": steps, "escalation": escalation}


def _extract_dict(result) -> dict | None:
    """MCP tool results may arrive as a dict, a JSON string, or a list of
    {type:text,text:...} content blocks. Find the payload dict with a score."""
    import json as _json

    def _try(x):
        if isinstance(x, dict):
            return x if "score" in x else None
        if isinstance(x, str):
            try:
                return _try(_json.loads(x))
            except Exception:
                return None
        if isinstance(x, list):
            for item in x:
                if isinstance(item, dict) and "text" in item:
                    got = _try(item["text"])
                else:
                    got = _try(item)
                if got is not None:
                    return got
        return None

    return _try(result)


def _maybe_escalate(question: str, steps: list[dict]) -> dict | None:
    """If the agent produced a risk score, run it through the HITL policy and
    write the audit trail — mirrors the production escalation path."""
    import json as _json
    import uuid

    from hitl import audit
    from hitl.escalation_policy import evaluate
    from hitl.models import EscalationRequest

    risk = next((s for s in steps if s["tool"] == "compliance_risk_score"), None)
    if not risk:
        return None
    data = _extract_dict(risk["result"])
    if data is None:
        return None

    req = EscalationRequest(
        entity=str(risk["args"].get("entity", "")),
        activity=str(risk["args"].get("activity", "")),
        risk_score=float(data.get("score", 0.0)),
        band=str(data.get("band", "")),
        sanctioned=bool(data.get("sanctioned", False)),
        pep=bool(data.get("pep", False)),
        watchlist=bool(data.get("watchlist", False)),
        factors=list(data.get("factors", [])),
    )
    decision = evaluate(req, get_settings().hitl_risk_threshold)
    if not decision.escalate:
        audit.record("auto_cleared", {"request": req.model_dump()})
        return {"escalated": False, "reasons": []}

    case_id = f"CASE-{uuid.uuid4().hex[:10]}"
    audit.record("escalated", {"case_id": case_id, "reasons": decision.reasons,
                               "request": req.model_dump()})
    return {"escalated": True, "case_id": case_id, "reasons": decision.reasons}


async def list_mcp_tools() -> list[str]:
    tools = await _mcp_client().get_tools()
    return [t.name for t in tools]
