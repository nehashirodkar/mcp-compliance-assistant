"""Thin demo server: a single page where you ask a compliance question and
watch the agent resolve the entity, score risk, cite the rule, and escalate.

Run:  .venv\\Scripts\\python.exe -m uvicorn demo.app:app --port 8801
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent.graph import answer_with_trace

app = FastAPI(title="compliance-demo")
_INDEX = Path(__file__).resolve().parent / "static" / "index.html"

# Never let a browser cache the page — edits must always take effect on reload.
_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


class AskInput(BaseModel):
    question: str


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(_INDEX.read_text(encoding="utf-8"), headers=_NO_CACHE)


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)  # silence the 404 noise


@app.post("/api/ask")
async def ask(body: AskInput) -> dict:
    q = (body.question or "").strip()
    if not q:
        return {"answer": "Please enter a question.", "steps": [], "escalation": None}
    return await answer_with_trace(q)
