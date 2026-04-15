"""Structured error logger → data/logs/error_log.json (append-only JSONL)."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field
from config.settings import LOG_DIR

LOG_FILE = LOG_DIR / "error_log.json"

ErrorCode = Literal["LLM_JSON_ERROR", "RETRIEVAL_MISS", "RUNTIME_FAIL"]


class ErrorEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().astimezone().isoformat())
    code: ErrorCode
    module: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    recovery_suggestion: str = ""


def log_error(entry: ErrorEntry) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def read_errors(limit: int = 100) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(l) for l in lines[-limit:]]
