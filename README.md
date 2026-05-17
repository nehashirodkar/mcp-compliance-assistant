<div align="center">

<img src="assets/banner.svg" alt="AEGIS — Agentic AML/KYC Compliance Assistant" width="100%" />

<br/>

**An MCP server exposing financial-compliance tools to an LLM agent — with defensive retries, memory, an eval-driven accuracy loop, human-in-the-loop escalation, and a single-page demo.**

<br/>

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-1.27-6E40C9)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-1C3C3C)
![LangChain](https://img.shields.io/badge/LangChain-1.3-1C3C3C?logo=langchain&logoColor=white)
![Anthropic](https://img.shields.io/badge/Claude-Sonnet%204.6-D4A27F?logo=anthropic&logoColor=white)
![Chroma](https://img.shields.io/badge/Chroma-1.5-FF6F61)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-48%20passing-2ea44f)
![License](https://img.shields.io/badge/license-MIT-blue)

[Architecture](#-architecture) · [Demo](#-demo) · [Quickstart](#-quickstart) · [Results](#-measured-results) · [Security](#-security)

<br/>

<img src="assets/demo.gif" alt="AEGIS demo — resolve entity, score AML risk, cite the BSA rule, escalate to human review" width="100%" />

<sub>Live agent: resolve customer → score AML risk → cite the controlling BSA clause → escalate high-risk cases with an audit trail.</sub>

</div>

---

## ⟡ What it is

**AEGIS** is a compliance assistant for **AML / KYC** workflows under the US Bank Secrecy Act. A LangGraph agent (Claude Sonnet 4.6) answers regulatory questions by calling three domain tools exposed over the **Model Context Protocol (MCP)**: it resolves a customer entity, scores its risk, and cites the controlling BSA/CIP clause — routing high-risk decisions to a human reviewer with an immutable audit trail.

> **Status: all 8 phases complete + working demo.** MCP server, 3 tools, live agent, memory, an eval loop that took citation accuracy **42% → 96%**, HITL escalation, hardening, and a single-page UI. 48 automated tests; agent + demo live-validated end-to-end.

## ⟡ Architecture

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'fontSize':'16px','fontFamily':'monospace',
  'primaryColor':'#ede9fe','primaryTextColor':'#1e1b2e','primaryBorderColor':'#7c3aed',
  'lineColor':'#7c3aed','textColor':'#1e1b2e',
  'clusterBkg':'#faf5ff','clusterBorder':'#7c3aed',
  'edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
    U([User / Compliance Q]):::io --> A
    DEMO[/Single-page demo/]:::io --> A

    subgraph AGENT["LangGraph Agent · Claude Sonnet 4.6"]
        A[ReAct loop]:::agent --> R[Retry guard]:::agent
        A <--> M[(Session +<br/>vector memory)]:::store
    end

    R -- stdio / MCP --> S

    subgraph S["MCP Server"]
        T1[regulatory_clause_lookup]:::tool
        T2[compliance_risk_score]:::tool
        T3[resolve_entity]:::tool
    end

    T1 --> C[(Chroma · local embeddings<br/>BSA / CIP / OFAC / FATF corpus)]:::store
    T3 --> E[(AML entity /<br/>watchlist table)]:::store
    T2 -. resolves internally .-> T3

    A -- risk score --> P{Escalation<br/>policy}:::policy
    P -- sanctioned / PEP / HIGH --> H[FastAPI HITL webhook<br/>API-key · rate-limit · req-id]:::hitl
    P -- clean --> CLR[Auto-cleared]:::ok
    H --> AUD[(Append-only<br/>audit log)]:::store
    A --> U

    classDef io fill:#c4b5fd,stroke:#5b21b6,stroke-width:2px,color:#1e1b2e,font-weight:bold;
    classDef agent fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#1e1b2e,font-weight:bold;
    classDef tool fill:#cffafe,stroke:#0e7490,stroke-width:2px,color:#0c2e34,font-weight:bold;
    classDef store fill:#fae8ff,stroke:#a21caf,stroke-width:2px,color:#3b0764,font-weight:bold;
    classDef policy fill:#fef9c3,stroke:#a16207,stroke-width:2px,color:#422006,font-weight:bold;
    classDef hitl fill:#fecaca,stroke:#b91c1c,stroke-width:2px,color:#450a0a,font-weight:bold;
    classDef ok fill:#bbf7d0,stroke:#15803d,stroke-width:2px,color:#052e16,font-weight:bold;
```

## ⟡ Demo

A single-page UI (cyber-noir, no build step): type a compliance question and watch the agent **resolve → score → cite → escalate** in real time, with the full tool trace and the escalation decision.

```powershell
.venv\Scripts\python.exe -m uvicorn demo.app:app --port 8801
# open http://127.0.0.1:8801
```

| Query | Behavior |
|---|---|
| *"When must a bank file a CTR?"* | clause lookup only — no risk score, no escalation |
| *"Onboarding risk for 'Volkov Petrochem'?"* | risk score → sanctioned → **escalated** (case ID + audit row) |
| *"Is 'Northwind Trading LLC' high-risk?"* | risk score → **auto-cleared** |

## ⟡ The three tools

| Tool | What it does | Implementation |
|------|--------------|----------------|
| `resolve_entity` | Fuzzy-matches a raw name to a canonical AML/KYC entity; surfaces `sanctioned` / `pep` / `watchlist` | `rapidfuzz` over names + aliases; confidence-thresholded and length-guarded to prevent false sanctions hits |
| `compliance_risk_score` | Customer risk rating (0–1 + band) with explainable factors; internally resolves the entity | **Deterministic rules only** — kept transparent and auditable on purpose (an LLM tie-break layer was scoped but intentionally omitted so every escalation has a defensible reason) |
| `regulatory_clause_lookup` | Semantic search over a BSA/CIP/OFAC/FATF corpus → citations + scores | Chroma RAG with a **local** embedding model — zero per-query token cost |

## ⟡ Quickstart

```powershell
# 1. Install
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. Secrets live OUTSIDE the repo (never committed, never diffed)
notepad $HOME\.mcp-compliance.env
#   ANTHROPIC_API_KEY=sk-ant-...        (required)
#   LANGSMITH_API_KEY=lsv2_...          (optional — eval tracing only)

# 3. Test  ·  4. Demo  ·  5. MCP server standalone
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m uvicorn demo.app:app --port 8801
.venv\Scripts\python.exe -m mcp_server.server
```

```python
import asyncio
from agent.graph import ask

print(asyncio.run(ask(
    "A new legal-entity customer wants to open an account. "
    "What identity and beneficial-ownership info must we collect? Cite the rule."
)))
```

## ⟡ Measured results

Real numbers from the LangSmith eval loop over a 24-item AML/KYC dataset — not targets.

**Answer accuracy (citation-correct):**

| Eval cycle | Accuracy | What changed |
|---|---:|---|
| 1 — baseline | 41.7% | Strict scorer (penalized correct answers for a `§` symbol) |
| 2 — scorer fixed | 83.3% | Citation-normalized scorer — *isolated a measurement artifact* |
| 3 — root-cause fixes | **95.8%** | Prompt citation discipline + removed a tool-filter footgun |
| 4 — cost-optimized | **95.8%** | Held accuracy while cutting cost; strict == normalized |

> The honest story isn't "73→87." **Trace-level failure analysis showed ~half the apparent failures were a broken evaluator, not the model** — and after fixing the real prompt/retrieval root causes the *strict* score caught up to the lenient one (no metric gaming).

**Cost & tooling:** mean cost/query **$0.0218 → $0.0132** (~39% / 1.65× reduction via redundant-round-trip elimination + cache-aware accounting). Tool-selection accuracy **100%**.

> ⚠️ **Honest limitation:** the original <$0.004 cost goal is **not met** (~3.3× over) and is structurally unreachable with a ReAct loop whose cacheable prefix falls under Anthropic's caching minimum. Stated as a real constraint, not hidden.

**HITL false-positive reduction:** the escalation policy removes **~83–100%** of flat-threshold false positives on the eval set, depending on modeled reviewer accuracy (sweep in `evals/analyze_hitl.py`) — reported as a sweep under explicit assumptions, not a single cherry-picked figure.

## ⟡ Security

| Concern | Mitigation |
|---|---|
| Secrets in repo / git / tool diffs | Resolved from OS env or a secrets file **outside the project tree** (`~/.mcp-compliance.env`); project `.env` is non-secret only |
| Unauthenticated webhook | `X-API-Key` auth on all data/mutation routes (`/health` open); fail-open only when no key is configured (documented dev mode) |
| Abuse / floods | In-memory sliding-window rate limiter → `429` + `Retry-After` |
| Traceability | `X-Request-ID` assigned/propagated + one structured JSON access log per request |
| Tamperable decision history | Append-only audit trail — no update/delete path; every escalation and review is recorded |

## ⟡ Project layout

```
mcp_server/   MCP server, 3 tools, Chroma index, seed corpora
agent/        LangGraph agent, retry guard, session + vector memory
hitl/         escalation policy, FastAPI webhook, audit trail, security
evals/        LangSmith dataset + runner + failure / HITL analysis
demo/         FastAPI single-page UI (resolve → score → cite → escalate)
config/       env-backed settings (secrets resolved out-of-repo)
tests/        48 tests — tools, retrieval, agent, memory, HITL, security
```

## ⟡ Roadmap

- [x] **Phase 1** — MCP skeleton, deps, server boots
- [x] **Phase 2** — 3 tools real + tested (entity / risk / clause)
- [x] **Phase 3** — LangGraph agent over MCP stdio, live-validated
- [x] **Phase 4** — session memory, Chroma long-term memory, retry guard
- [x] **Phase 5** — LangSmith eval harness + baseline (cost-aware scorer)
- [x] **Phase 6** — trace-driven iteration: 41.7% → 95.8%, cost −39%
- [x] **Phase 7** — FastAPI HITL escalation + append-only audit trail
- [x] **Phase 8** — hardening: API-key auth, rate limiting, request-id logging
- [x] **Demo** — single-page UI, live-validated

<div align="center">
<br/>
<sub>Built with the Claude Agent SDK · cyber-noir · EST. 2026</sub>
</div>
