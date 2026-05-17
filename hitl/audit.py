"""Append-only audit trail for every escalated agent action.

Immutable by construction: the only write path is append. There is no update
or delete API — the audit log is the compliance evidence trail.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from config.settings import get_settings

_LOCK = threading.Lock()


def _audit_path() -> Path:
    p = Path(os.getenv("HITL_AUDIT_PATH", get_settings().hitl_audit_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(event_type: str, payload: dict) -> dict:
    """Append one timestamped, immutable row. Returns the written row."""
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "payload": payload,
    }
    line = json.dumps(row, default=str, ensure_ascii=False)
    with _LOCK:
        with _audit_path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return row


def read_all() -> list[dict]:
    p = _audit_path()
    if not p.exists():
        return []
    return [
        json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
