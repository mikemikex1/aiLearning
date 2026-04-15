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
from typing import Iterable, Literal, TypedDict
from src.rag.parent_retriever import retrieve
from src.models.router import call_with_fallback


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
    "numbered context block. If the context is insufficient, say so.\n\n"
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


def answer(
    query: str,
    k: int = 4,
    history: list[tuple[str, str]] | None = None,
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
    )
    reply = call_with_fallback("complex", prompt)
    citations = [_build_citation(i, c) for i, c in enumerate(chunks)]
    return {"answer": reply, "sources": citations}
