"""Central config.

Secrets never live in the repo. Non-secret config comes from the project
.env; secrets (API keys) are resolved from the OS environment or from a
secrets file that lives OUTSIDE the project tree, so no in-repo file-change
diff can ever surface them.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# Project .env holds non-secret config only. override=True so a shell that
# exports an empty value cannot shadow the .env value.
load_dotenv(override=True)

# Secrets file, outside the project dir. Override location with MCP_SECRETS_FILE.
_DEFAULT_SECRETS_FILE = Path.home() / ".mcp-compliance.env"


def _secrets_file() -> Path:
    return Path(os.environ.get("MCP_SECRETS_FILE", str(_DEFAULT_SECRETS_FILE)))


@lru_cache(maxsize=1)
def _secrets() -> dict[str, str]:
    p = _secrets_file()
    return {k: v for k, v in dotenv_values(p).items() if v} if p.exists() else {}


def _secret(name: str) -> str:
    """OS env wins (if non-empty), else the out-of-repo secrets file."""
    return os.environ.get(name) or _secrets().get(name) or ""


class Settings:
    anthropic_api_key: str = _secret("ANTHROPIC_API_KEY")
    langsmith_api_key: str = _secret("LANGSMITH_API_KEY")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "mcp-compliance-assistant")

    agent_model: str = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
    eval_model: str = os.getenv("EVAL_MODEL", "claude-opus-4-7")

    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./.chroma")

    hitl_webhook_port: int = int(os.getenv("HITL_WEBHOOK_PORT", "8000"))
    hitl_risk_threshold: float = float(os.getenv("HITL_RISK_THRESHOLD", "0.75"))
    hitl_audit_path: str = os.getenv("HITL_AUDIT_PATH", "./.audit/hitl_audit.jsonl")
    hitl_api_key: str = _secret("HITL_API_KEY")
    rate_limit_max: int = int(os.getenv("RATE_LIMIT_MAX", "30"))
    rate_limit_window_s: int = int(os.getenv("RATE_LIMIT_WINDOW_S", "60"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
