"""Model Router: cost-aware selection between Flash-Lite and Flash.

Reads user_settings.json on every call so the Settings page can change
routing live without a restart.

Rules
-----
- `simple`  → routing.simple_model  (default: flash-lite)
- `complex` → routing.complex_model (default: flash)
- On 429 / ResourceExhausted → exponential backoff
- If routing.downgrade_on_429 is True, complex downgrades to simple on
  repeated 429 during the same call.
"""
from __future__ import annotations
import time
from typing import Literal
from langchain_google_genai import ChatGoogleGenerativeAI
from config.settings import MODEL_LITE, MODEL_FLASH, get_api_key, get_routing

TaskKind = Literal["simple", "complex"]


def pick_model(task: TaskKind) -> str:
    r = get_routing()
    if task == "complex":
        return r.get("complex_model", MODEL_FLASH)
    return r.get("simple_model", MODEL_LITE)


def make_llm(task: TaskKind, temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=pick_model(task),
        google_api_key=get_api_key(),
        temperature=temperature,
    )


def call_with_fallback(task: TaskKind, prompt: str, max_retries: int = 3) -> str:
    """Call LLM with exponential backoff; optional downgrade on repeated 429."""
    routing = get_routing()
    allow_downgrade = bool(routing.get("downgrade_on_429", True))
    current: TaskKind = task
    for attempt in range(max_retries):
        try:
            llm = make_llm(current)
            return llm.invoke(prompt).content
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            if "429" in msg or "quota" in msg or "resource" in msg:
                time.sleep(2 ** attempt)
                if (allow_downgrade and attempt == max_retries - 2
                        and current == "complex"):
                    current = "simple"
                continue
            raise
    raise RuntimeError(f"Model router exhausted retries for task={task}")
