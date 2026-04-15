"""Browser & RAG Agent — fetch → clean → chunk → ingest."""
from __future__ import annotations
import json
from src.sources.collectors import collect_all
from src.rag.parent_retriever import ingest
from src.models.router import call_with_fallback
from src.utils.error_handler import record
from config.settings import load_keywords

CLEAN_PROMPT = (
    "You are a content cleaner. Strip HTML/markup noise and return a concise, "
    "information-dense version of the following. Keep code blocks verbatim.\n\n---\n{t}\n---"
)


def clean_text(raw: str) -> str:
    if not raw.strip():
        return ""
    try:
        return call_with_fallback("simple", CLEAN_PROMPT.format(t=raw[:4000]))
    except Exception as e:  # noqa: BLE001
        record("LLM_JSON_ERROR", "browser_rag.clean_text", str(e))
        return raw[:4000]


def run_daily_ingest() -> dict:
    keywords = load_keywords()
    path = collect_all(keywords=keywords)
    payload = json.loads(path.read_text())
    items = payload.get("items", [])
    docs = []
    for it in items:
        text = clean_text(f"{it['title']}\n\n{it['summary']}")
        if not text:
            continue
        docs.append({
            "text": text,
            "metadata": {"source": it["source"], "link": it["link"],
                         "title": it["title"], "published": it["published"],
                         "fetched_at": it.get("fetched_at", "")},
        })
    n = ingest(docs)
    return {"collected": len(items), "ingested_parents": n,
            "raw_file": str(path), "fetched_at": payload.get("fetched_at", "")}
