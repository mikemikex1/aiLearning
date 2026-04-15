"""News curator — LLM picks daily top-3 and persists the result.

Picks are cached to `data/raw/<date>/top3.json` so we never pay the
LLM twice for the same day unless the caller passes `force=True`.
"""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from src.models.router import call_with_fallback
from src.utils.error_handler import record
from config.settings import RAW_DIR


PICK_PROMPT = """From the list of AI-related items below, pick the 3 most
important for a learner today. Return STRICT JSON in this exact shape (no
prose, no markdown fences):

{{"picks": [
  {{"rank": 1, "title": "...", "link": "...", "justification": "one sentence"}},
  {{"rank": 2, "title": "...", "link": "...", "justification": "one sentence"}},
  {{"rank": 3, "title": "...", "link": "...", "justification": "one sentence"}}
]}}

Items:
{items}
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in LLM response")
    return json.loads(m.group(0))


def _load_collected(date_str: str) -> list[dict]:
    f = RAW_DIR / date_str / "collected.json"
    if not f.exists():
        return []
    payload = json.loads(f.read_text())
    if isinstance(payload, dict):
        return payload.get("items", [])
    return payload  # legacy list shape


def top3_path(date_str: str) -> Path:
    return RAW_DIR / date_str / "top3.json"


def load_top3(date_str: str) -> dict | None:
    p = top3_path(date_str)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def pick_top3(date_str: str, force: bool = False) -> dict:
    """Return a cached or freshly-picked top-3 payload for `date_str`.

    Payload shape:
        {
          "date": "YYYY-MM-DD",
          "picked_at": "<timestamptz>",
          "model": "<model id>",
          "picks": [{"rank","title","link","justification"}, ...]
        }
    """
    if not force:
        cached = load_top3(date_str)
        if cached:
            return cached

    items = _load_collected(date_str)
    if not items:
        return {"date": date_str, "picked_at": _now_iso(),
                "model": "", "picks": [],
                "error": f"no collected.json for {date_str}"}

    # Cap item list to keep the prompt small
    condensed = "\n".join(
        f"- {i.get('title','?')} | {i.get('link','')}" for i in items[:40]
    )

    try:
        raw = call_with_fallback("complex", PICK_PROMPT.format(items=condensed))
        parsed = _extract_json(raw)
        picks = parsed.get("picks", [])[:3]
    except Exception as e:  # noqa: BLE001
        record("LLM_JSON_ERROR", "news_curator.pick_top3", str(e),
               {"date": date_str})
        return {"date": date_str, "picked_at": _now_iso(),
                "model": "", "picks": [], "error": str(e)}

    payload = {
        "date": date_str,
        "picked_at": _now_iso(),
        "model": "complex",  # exact model is decided by router at call time
        "picks": picks,
    }
    top3_path(date_str).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def list_all_top3() -> list[dict]:
    """Return every persisted top-3 payload, newest date first."""
    out: list[dict] = []
    if not RAW_DIR.exists():
        return out
    for d in sorted([p for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True):
        p = d / "top3.json"
        if p.exists():
            try:
                out.append(json.loads(p.read_text()))
            except Exception:  # noqa: BLE001
                continue
    return out
