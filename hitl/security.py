"""Hardening for the HITL webhook: API-key auth, in-memory rate limiting,
and structured request-ID access logging.

Config is read dynamically (env first, then settings) so it is testable
without process restarts.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import get_settings

_log = logging.getLogger("hitl.access")
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)


def _expected_key() -> str:
    return os.getenv("HITL_API_KEY") or get_settings().hitl_api_key


def _rl_config() -> tuple[int, int]:
    s = get_settings()
    return (
        int(os.getenv("RATE_LIMIT_MAX", str(s.rate_limit_max))),
        int(os.getenv("RATE_LIMIT_WINDOW_S", str(s.rate_limit_window_s))),
    )


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = _expected_key()
    if not expected:
        # No key configured → auth disabled (local dev). Fail open by design,
        # documented; production sets HITL_API_KEY.
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


_HITS: dict[str, deque[float]] = defaultdict(deque)


async def rate_limit(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    max_req, window = _rl_config()
    ident = x_api_key or (request.client.host if request.client else "anon")
    now = time.time()
    dq = _HITS[ident]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= max_req:
        raise HTTPException(
            status_code=429,
            detail=f"rate limit exceeded ({max_req}/{window}s)",
            headers={"Retry-After": str(window)},
        )
    dq.append(now)


def reset_rate_limit() -> None:
    _HITS.clear()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates X-Request-ID and emits one structured access log."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        start = time.time()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        _log.info(
            json.dumps(
                {
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.time() - start) * 1000, 1),
                }
            )
        )
        return response
