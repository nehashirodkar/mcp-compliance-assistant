"""LangSmith eval runner — the accuracy + cost iteration loop.

Scores each item on:
  - citation correctness  (primary "compliance answer accuracy")
  - tool-selection correctness
  - token cost / query     (the <$0.004 target)

Results are written to evals/results/<ts>.json and, if LANGSMITH_TRACING is
on, every agent run is traced to LangSmith for failure analysis (Phase 6).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from config.settings import get_settings

# Export tracing env BEFORE importing the agent so LangChain picks it up.
_s = get_settings()
if _s.langsmith_api_key:
    os.environ.setdefault("LANGSMITH_API_KEY", _s.langsmith_api_key)
    os.environ.setdefault("LANGCHAIN_API_KEY", _s.langsmith_api_key)
os.environ.setdefault("LANGSMITH_PROJECT", _s.langsmith_project)
# The eval runner is exactly where we want traces — force-enable when a key
# is present, regardless of the app-wide .env flag.
if _s.langsmith_api_key:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"

from langchain_core.messages import HumanMessage  # noqa: E402

from agent.graph import build_agent  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_DATASET = _ROOT / "evals" / "datasets" / "aml_kyc.jsonl"
_RESULTS_DIR = _ROOT / "evals" / "results"

# Sonnet-tier pricing estimate, USD per million tokens. Override via env.
_PRICE_IN = float(os.getenv("PRICE_IN_PER_MTOK", "3.00"))
_PRICE_OUT = float(os.getenv("PRICE_OUT_PER_MTOK", "15.00"))


def _load_dataset() -> list[dict]:
    return [json.loads(line) for line in _DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(s: str) -> str:
    """Normalize a citation for matching: drop section signs, punctuation,
    casing and whitespace so '31 CFR § 1010.313' == '31 CFR 1010.313'."""
    s = s.lower().replace("§", " ").replace("c.f.r.", "cfr").replace("u.s.c.", "usc")
    return "".join(ch for ch in s if ch.isalnum())


def _tool_names(messages: list) -> set[str]:
    names: set[str] = set()
    for m in messages:
        for tc in getattr(m, "tool_calls", []) or []:
            n = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if n:
                names.add(n)
    return names


def _token_cost(messages: list) -> tuple[int, int, float]:
    """Cache-aware cost. Anthropic prices cached reads at 0.1x input and
    cache writes at 1.25x; billing all input at 1x over-reports cost."""
    tin = tout = 0
    cost = 0.0
    for m in messages:
        u = getattr(m, "usage_metadata", None)
        if not u:
            continue
        out = u.get("output_tokens", 0)
        total_in = u.get("input_tokens", 0)
        det = u.get("input_token_details", {}) or {}
        cr = det.get("cache_read", 0) or 0
        cc = det.get("cache_creation", 0) or 0
        fresh = max(total_in - cr - cc, 0)
        cost += (
            fresh * _PRICE_IN
            + cr * _PRICE_IN * 0.1
            + cc * _PRICE_IN * 1.25
            + out * _PRICE_OUT
        ) / 1_000_000
        tin += total_in
        tout += out
    return tin, tout, cost


async def _run_item(agent, item: dict) -> dict:
    sid = f"eval-{item['id']}-{uuid.uuid4().hex[:6]}"
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=item["question"])]},
        config={"configurable": {"thread_id": sid}},
    )
    messages = result["messages"]
    answer = messages[-1].content
    if isinstance(answer, list):  # content blocks -> text
        answer = " ".join(b.get("text", "") for b in answer if isinstance(b, dict))

    norm_answer = _norm(answer)
    citation_hit = any(_norm(c) in norm_answer for c in item["expected_citations"])
    citation_hit_strict = any(c in answer for c in item["expected_citations"])
    called = _tool_names(messages)
    tool_hit = set(item["expected_tools"]).issubset(called)
    tin, tout, cost = _token_cost(messages)

    return {
        "id": item["id"],
        "citation_hit": citation_hit,
        "citation_hit_strict": citation_hit_strict,
        "tool_hit": tool_hit,
        "tools_called": sorted(called),
        "tokens_in": tin,
        "tokens_out": tout,
        "cost_usd": round(cost, 6),
        "answer": answer,
        "answer_preview": answer[:200],
    }


async def main() -> None:
    dataset = _load_dataset()
    agent = await build_agent()

    rows: list[dict] = []
    for i, item in enumerate(dataset, 1):
        r = await _run_item(agent, item)
        rows.append(r)
        flag = "OK " if r["citation_hit"] else "MISS"
        print(f"[{i:2}/{len(dataset)}] {r['id']:<8} {flag} "
              f"cite={int(r['citation_hit'])} tool={int(r['tool_hit'])} "
              f"${r['cost_usd']:.5f}")

    n = len(rows)
    acc = sum(r["citation_hit"] for r in rows) / n
    acc_strict = sum(r["citation_hit_strict"] for r in rows) / n
    tool_acc = sum(r["tool_hit"] for r in rows) / n
    mean_cost = sum(r["cost_usd"] for r in rows) / n
    max_cost = max(r["cost_usd"] for r in rows)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": _s.agent_model,
        "n": n,
        "answer_accuracy": round(acc, 4),
        "answer_accuracy_strict": round(acc_strict, 4),
        "tool_accuracy": round(tool_acc, 4),
        "mean_cost_usd": round(mean_cost, 6),
        "max_cost_usd": round(max_cost, 6),
        "rows": rows,
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _RESULTS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 52)
    print(f"  answer accuracy : {acc:6.1%}  ({sum(r['citation_hit'] for r in rows)}/{n})  [normalized]")
    print(f"  answer accuracy : {acc_strict:6.1%}  ({sum(r['citation_hit_strict'] for r in rows)}/{n})  [strict / old ruler]")
    print(f"  tool accuracy   : {tool_acc:6.1%}")
    print(f"  mean cost/query : ${mean_cost:.5f}   (target < $0.004)")
    print(f"  max  cost/query : ${max_cost:.5f}")
    print(f"  results         : {out.relative_to(_ROOT)}")
    print("=" * 52)


if __name__ == "__main__":
    asyncio.run(main())
