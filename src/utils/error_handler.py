"""Helpers for structured error handling with Gemini-authored recovery hints."""
from __future__ import annotations
from src.schemas.error_log import ErrorEntry, log_error, ErrorCode
from src.models.router import call_with_fallback


def record(code: ErrorCode, module: str, message: str, context: dict | None = None) -> None:
    try:
        suggestion = call_with_fallback(
            "simple",
            f"Give a one-sentence actionable recovery suggestion for this error.\n"
            f"code={code}\nmodule={module}\nmessage={message}\ncontext={context}"
        )
    except Exception:
        suggestion = "Check logs and retry with exponential backoff."
    log_error(ErrorEntry(
        code=code, module=module, message=message,
        context=context or {}, recovery_suggestion=suggestion,
    ))
