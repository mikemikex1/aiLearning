"""Search Agent: indexed RAG retrieval + language-aware synthesis + product skill."""
from __future__ import annotations

import re
from typing import Iterable, Literal, TypedDict

from src.agents.product_skill import (
    is_app_navigation_query,
    local_app_navigation_answer,
    product_skill_text,
)
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
    "You are a focused learning assistant.\n"
    "Use ONLY the context blocks for factual claims and cite as [n].\n"
    "You may use Product Skill Context only for app-page navigation guidance.\n"
    "Write the final answer in {answer_language}.\n\n"
    "Product Skill Context:\n{product_skill}\n\n"
    "Conversation:\n{history}\n\n"
    "Question: {q}\n\n"
    "Context:\n{ctx}\n"
)

APP_HELP_TEMPLATE = (
    "You are an in-app guide.\n"
    "Answer in {answer_language}.\n"
    "Use this Product Skill Context only, and give concise page-level guidance.\n\n"
    "{product_skill}\n\n"
    "User question: {q}\n"
)

FOLLOWUP_TERMS = {
    "zh": {"想知道更多", "更多", "繼續", "延伸", "細節", "補充", "再說明"},
    "en": {"tell me more", "more", "continue", "elaborate", "details", "expand"},
}

INSUFFICIENT_PATTERNS = {
    "zh": {"上下文不足", "資訊不足", "無法回答", "提供內容不足"},
    "en": {"insufficient context", "not enough context", "cannot answer", "insufficient information"},
}


def _detect_locale_from_text(text: str, fallback: str = "zh-TW") -> str:
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    en_count = len(re.findall(r"[A-Za-z]", text or ""))
    if zh_count >= 2 and zh_count >= en_count:
        return "zh-TW"
    if en_count >= 6 and en_count > zh_count:
        return "en-US"
    return fallback


def _resolve_answer_locale(query: str, history: list[tuple[str, str]] | None, fallback: str) -> str:
    by_query = _detect_locale_from_text(query, "")
    if by_query:
        return by_query
    for role, msg in reversed(history or []):
        if role in ("user", "human") and msg.strip():
            by_history = _detect_locale_from_text(msg, "")
            if by_history:
                return by_history
    return fallback if fallback in ("zh-TW", "en-US") else "zh-TW"


def _format_history(history: Iterable[tuple[str, str]] | None) -> str:
    if not history:
        return "(none)"
    lines: list[str] = []
    for role, content in list(history)[-6:]:
        prefix = "User" if role in ("user", "human") else "Assistant"
        lines.append(f"{prefix}: {content[:500]}")
    return "\n".join(lines)


def _build_citation(index: int, chunk: dict) -> Citation:
    meta = chunk.get("metadata", {}) or {}
    source_type: Literal["web", "project"] = "project" if meta.get("source") == "project" else "web"
    text = chunk.get("text") or ""
    return Citation(
        source_type=source_type,
        title=meta.get("title") or meta.get("project_id") or f"source-{index}",
        link=meta.get("link", ""),
        kind=meta.get("kind", meta.get("source", "")),
        file=meta.get("file", ""),
        snippet=text[:220].replace("\n", " "),
        parent_text=text,
    )


def _concise_title(title: str, max_len: int = 80) -> str:
    value = re.sub(r"\s+", " ", (title or "")).strip()
    return value if len(value) <= max_len else value[: max_len - 1].rstrip() + "..."


def _is_followup_query(query: str, locale: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False
    if locale == "zh-TW":
        return len(q) <= 8 or any(term in q for term in FOLLOWUP_TERMS["zh"])
    return len(q.split()) <= 3 or any(term in q for term in FOLLOWUP_TERMS["en"])


def _expand_retrieval_query(query: str, history: list[tuple[str, str]] | None, locale: str) -> str:
    if not history:
        return query
    if not _is_followup_query(query, locale):
        return query
    recent_user = [content.strip() for role, content in history if role in ("user", "human") and content.strip()]
    anchor = " ".join(recent_user[-2:])
    return f"{anchor}\n{query}".strip() if anchor else query


def _build_local_summary(chunks: list[dict], k: int, locale: str) -> str:
    if locale == "zh-TW":
        lines = ["根據已索引內容，我先整理重點如下："]
        for i, chunk in enumerate(chunks[:k], 1):
            meta = chunk.get("metadata", {}) or {}
            title = meta.get("title", f"來源 {i}")
            snippet = (chunk.get("text", "") or "").replace("\n", " ")[:520]
            lines.append(f"{i}. {title}：{snippet}...")
        return "\n".join(lines)
    lines = ["Here are key points from indexed context:"]
    for i, chunk in enumerate(chunks[:k], 1):
        meta = chunk.get("metadata", {}) or {}
        title = meta.get("title", f"Source {i}")
        snippet = (chunk.get("text", "") or "").replace("\n", " ")[:520]
        lines.append(f"{i}. {title}: {snippet}...")
    return "\n".join(lines)


def _looks_insufficient_reply(reply: str, locale: str) -> bool:
    txt = (reply or "").lower()
    patterns = INSUFFICIENT_PATTERNS["zh"] if locale == "zh-TW" else INSUFFICIENT_PATTERNS["en"]
    return any(p in txt for p in patterns)


def suggest_prompts(
    query: str = "",
    history: list[tuple[str, str]] | None = None,
    locale: str = "zh-TW",
    max_suggestions: int = 3,
) -> list[str]:
    """Return title-only suggestions from indexed content."""
    items = list_indexed_items(limit=120)
    if not items:
        return []

    query_blob = " ".join([query, *[c for _, c in (history or [])[-4:]]]).lower().strip()
    tokens = re.findall(r"[a-zA-Z0-9\-\+\u4e00-\u9fff]{2,}", query_blob)[:12]

    scored: list[tuple[int, dict]] = []
    for item in items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        text = f"{title} {summary}".lower()
        score = 1
        if locale == "zh-TW" and item.get("language") == "zh":
            score += 1
        if locale != "zh-TW" and item.get("language") == "en":
            score += 1
        for token in tokens:
            if token in text:
                score += 2
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    suggestions: list[str] = []
    for _, item in scored:
        title = _concise_title(item.get("title", ""))
        if title and title not in suggestions:
            suggestions.append(title)
        if len(suggestions) >= max_suggestions:
            break
    return suggestions


def _answer_app_navigation(query: str, locale: str) -> str:
    prompt = APP_HELP_TEMPLATE.format(
        answer_language="Traditional Chinese" if locale == "zh-TW" else "English",
        product_skill=product_skill_text(locale),
        q=query,
    )
    try:
        return call_with_fallback("simple", prompt)
    except Exception:
        return local_app_navigation_answer(locale)


def answer(
    query: str,
    k: int = 4,
    history: list[tuple[str, str]] | None = None,
    locale: str = "zh-TW",
) -> dict:
    effective_locale = _resolve_answer_locale(query, history, locale)

    if is_app_navigation_query(query):
        return {"answer": _answer_app_navigation(query, effective_locale), "sources": []}

    retrieval_query = _expand_retrieval_query(query, history, effective_locale)
    chunks = retrieve(retrieval_query, k=k)
    if not chunks and retrieval_query != query:
        chunks = retrieve(query, k=k)

    if not chunks:
        if effective_locale == "zh-TW":
            return {
                "answer": "目前找不到已索引的上下文。請先執行 ingest，或提供更具體關鍵字。",
                "sources": [],
            }
        return {
            "answer": "No indexed context found yet. Run ingest first, or ask with more specific keywords.",
            "sources": [],
        }

    numbered_ctx = "\n\n".join(
        f"[{i + 1}] ({c['metadata'].get('source', '?')}) {c['metadata'].get('title', '?')}\n{c['text']}"
        for i, c in enumerate(chunks)
    )
    prompt = TEMPLATE.format(
        answer_language="Traditional Chinese" if effective_locale == "zh-TW" else "English",
        product_skill=product_skill_text(effective_locale),
        history=_format_history(history),
        q=query,
        ctx=numbered_ctx,
    )

    try:
        reply = call_with_fallback("complex", prompt)
        if _looks_insufficient_reply(reply, effective_locale):
            reply = _build_local_summary(chunks, k, effective_locale)
    except Exception:
        reply = _build_local_summary(chunks, k, effective_locale)
        if effective_locale == "zh-TW":
            reply += "\n\n目前無法連線到雲端模型，已先提供本地整理重點。"
        else:
            reply += "\n\nCloud model is temporarily unavailable. Local summary is provided."

    citations = [_build_citation(i, chunk) for i, chunk in enumerate(chunks)]
    return {"answer": reply, "sources": citations}
