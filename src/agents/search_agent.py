"""Search Agent — RAG retrieval + LLM synthesis.

Upgrades over v0.1:
- Project-aware: same Parent-Document store now also holds indexed projects
  (blueprint / main.py / stability_report), tagged with source=`project`.
- Conversation memory: accepts a list of prior (role, content) turns and
  feeds a condensed history into the prompt so follow-ups resolve correctly.
- Richer citations: each hit returns kind, source type, file / link, and a
  short snippet for UI rendering.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Iterable, Literal, TypedDict
from src.rag.parent_retriever import retrieve
from src.models.router import call_with_fallback
from config.settings import RAW_DIR


class Citation(TypedDict, total=False):
    source_type: Literal["web", "project"]
    title: str
    link: str
    kind: str          # blueprint | code | stability_report | rss | ...
    file: str
    snippet: str       # first ~220 chars for inline preview
    parent_text: str   # full parent chunk (~1500 chars)


TEMPLATE = (
    "You are a focused learning assistant. Answer the user's question using "
    "ONLY the context below. Cite sources inline as [n] where n matches the "
    "numbered context block. If the context is insufficient, say so.\n"
    "Write the final answer in {answer_language}.\n\n"
    "Conversation so far:\n{history}\n\n"
    "Question: {q}\n\n"
    "Context:\n{ctx}\n"
)


def _format_history(history: Iterable[tuple[str, str]] | None) -> str:
    if not history:
        return "(none)"
    lines = []
    for role, content in list(history)[-6:]:  # last 3 turns each side
        prefix = "User" if role in ("user", "human") else "Assistant"
        lines.append(f"{prefix}: {content[:400]}")
    return "\n".join(lines)


def _build_citation(i: int, c: dict) -> Citation:
    m = c.get("metadata", {}) or {}
    source_type: Literal["web", "project"] = (
        "project" if m.get("source") == "project" else "web"
    )
    full_text = c.get("text") or ""
    snippet = full_text[:220].replace("\n", " ")
    return Citation(
        source_type=source_type,
        title=m.get("title") or m.get("project_id") or f"source-{i}",
        link=m.get("link", ""),
        kind=m.get("kind", m.get("source", "")),
        file=m.get("file", ""),
        snippet=snippet,
        parent_text=full_text,
    )


def _latest_items(limit: int = 60) -> list[dict]:
    dates = sorted([p for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True)
    for d in dates:
        p = d / "collected.json"
        if not p.exists():
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            items = payload.get("items", [])
            if isinstance(items, list):
                real_items = [it for it in items if (it.get("source") != "test")]
                return real_items[:limit]
        except Exception:
            continue
    return []


def _concise_title(title: str, max_len: int = 54) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"


def suggest_prompts(
    query: str = "",
    history: list[tuple[str, str]] | None = None,
    locale: str = "zh-TW",
    max_suggestions: int = 5,
) -> list[str]:
    """Generate concise quick-pick prompts from latest fetched items + user context."""
    q = (query or "").strip().lower()
    history_blob = " ".join([c for _, c in (history or [])[-4:]]).lower()
    blob = f"{q} {history_blob}".strip()
    items = _latest_items(limit=80)
    if not items:
        return []

    scored: list[tuple[int, dict]] = []
    for it in items:
        title = (it.get("title") or "")
        summary = (it.get("summary") or "")
        text = f"{title} {summary}".lower()
        score = 0
        if blob:
            for token in re.findall(r"[a-zA-Z0-9\-\+]{3,}", blob)[:8]:
                if token in text:
                    score += 1
        if it.get("source") == "hf_papers":
            score += 1
        scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [it for _, it in scored[: max_suggestions * 2]]

    out: list[str] = []
    for it in picked:
        title = _concise_title(it.get("title", ""))
        if locale == "zh-TW":
            prompt = f"這篇文章重點：{title}"
        else:
            prompt = f"Key takeaway from this article: {title}"
        if prompt not in out:
            out.append(prompt)
        if len(out) >= max_suggestions:
            break
    return out


def answer(
    query: str,
    k: int = 4,
    history: list[tuple[str, str]] | None = None,
    locale: str = "zh-TW",
) -> dict:
    chunks = retrieve(query, k=k)
    if not chunks:
        return {
            "answer": "No relevant context in RAG yet. Run daily ingest first.",
            "sources": [],
        }
    numbered_ctx = "\n\n".join(
        f"[{i+1}] ({c['metadata'].get('source','?')}) "
        f"{c['metadata'].get('title','?')}\n{c['text']}"
        for i, c in enumerate(chunks)
    )
    prompt = TEMPLATE.format(
        history=_format_history(history),
        q=query,
        ctx=numbered_ctx,
        answer_language="Traditional Chinese" if locale == "zh-TW" else "English",
    )
    try:
        reply = call_with_fallback("complex", prompt)
    except Exception:
        # Offline/network-failure fallback: return a deterministic local summary.
        if locale == "zh-TW":
            lines = [
                "目前無法連線到雲端模型，以下為本地整理重點：",
            ]
            for i, c in enumerate(chunks[:k], 1):
                m = c.get("metadata", {}) or {}
                title = m.get("title", f"來源 {i}")
                snippet = (c.get("text", "") or "").replace("\n", " ")[:180]
                lines.append(f"{i}. {title}：{snippet}...")
            lines.append("建議稍後重試以取得完整生成式回答。")
            reply = "\n".join(lines)
        else:
            lines = [
                "Cloud model is currently unreachable. Local fallback summary:",
            ]
            for i, c in enumerate(chunks[:k], 1):
                m = c.get("metadata", {}) or {}
                title = m.get("title", f"Source {i}")
                snippet = (c.get("text", "") or "").replace("\n", " ")[:180]
                lines.append(f"{i}. {title}: {snippet}...")
            lines.append("Please retry later for a full generated answer.")
            reply = "\n".join(lines)
    citations = [_build_citation(i, c) for i, c in enumerate(chunks)]
    return {"answer": reply, "sources": citations}
