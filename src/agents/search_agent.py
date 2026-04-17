"""Search Agent: RAG retrieval + suggestion prompts + synthesis."""
from __future__ import annotations

import re
from typing import Iterable, Literal, TypedDict

from src.models.router import call_with_fallback
from src.rag.parent_retriever import list_indexed_items, retrieve


class Citation(TypedDict, total=False):
    source_type: Literal["web", "project"]
    title: str
    link: str
    kind: str
    file: str
    snippet: str
    parent_text: str


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
    for role, content in list(history)[-6:]:
        prefix = "User" if role in ("user", "human") else "Assistant"
        lines.append(f"{prefix}: {content[:400]}")
    return "\n".join(lines)


def _build_citation(i: int, c: dict) -> Citation:
    m = c.get("metadata", {}) or {}
    source_type: Literal["web", "project"] = "project" if m.get("source") == "project" else "web"
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


def _concise_title(title: str, max_len: int = 58) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "..."


def suggest_prompts(
    query: str = "",
    history: list[tuple[str, str]] | None = None,
    locale: str = "zh-TW",
    max_suggestions: int = 5,
) -> list[str]:
    """Generate concise quick prompts from *indexed* items only."""
    q = (query or "").strip().lower()
    history_blob = " ".join([c for _, c in (history or [])[-4:]]).lower()
    blob = f"{q} {history_blob}".strip()

    items = list_indexed_items(limit=120)
    if not items:
        return []

    scored: list[tuple[int, dict]] = []
    for it in items:
        title = it.get("title", "")
        summary = it.get("summary", "")
        text = f"{title} {summary}".lower()
        score = 1
        if blob:
            for token in re.findall(r"[a-zA-Z0-9\-\+\u4e00-\u9fff]{2,}", blob)[:10]:
                if token in text:
                    score += 2
        if it.get("source") == "hf_papers":
            score += 1
        scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [it for _, it in scored[: max_suggestions * 2]]

    out: list[str] = []
    for it in picked:
        title = _concise_title(it.get("title", ""))
        if locale == "zh-TW":
            prompt = f"請用三點說明：{title}"
        else:
            prompt = f"Explain in 3 bullet points: {title}"
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
            "answer": (
                "目前找不到已入庫的相關內容，請先執行 ingest。"
                if locale == "zh-TW"
                else "No indexed context found yet. Please run ingest first."
            ),
            "sources": [],
        }

    numbered_ctx = "\n\n".join(
        f"[{i+1}] ({c['metadata'].get('source','?')}) {c['metadata'].get('title','?')}\n{c['text']}"
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
        # Network-safe fallback summary.
        if locale == "zh-TW":
            lines = ["目前無法連線到雲端模型，以下為本地整理重點："]
            for i, c in enumerate(chunks[:k], 1):
                m = c.get("metadata", {}) or {}
                title = m.get("title", f"來源 {i}")
                snippet = (c.get("text", "") or "").replace("\n", " ")[:420]
                lines.append(f"{i}. {title}：{snippet}...")
            lines.append("建議稍後重試以取得完整生成式回答。")
            reply = "\n".join(lines)
        else:
            lines = ["Cloud model is currently unreachable. Local fallback summary:"]
            for i, c in enumerate(chunks[:k], 1):
                m = c.get("metadata", {}) or {}
                title = m.get("title", f"Source {i}")
                snippet = (c.get("text", "") or "").replace("\n", " ")[:420]
                lines.append(f"{i}. {title}: {snippet}...")
            lines.append("Please retry later for a full generated answer.")
            reply = "\n".join(lines)

    citations = [_build_citation(i, c) for i, c in enumerate(chunks)]
    return {"answer": reply, "sources": citations}
