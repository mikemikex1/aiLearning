"""News curator for Daily Learning Top-3 (V1).

This module builds daily learning cards from indexed RAG items only.
Results are cached to `data/raw/<date>/top3.json`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from config.settings import RAW_DIR, load_keywords
from src.rag.parent_retriever import list_indexed_items

STOPWORDS_EN = {
    "the",
    "a",
    "an",
    "to",
    "for",
    "of",
    "and",
    "in",
    "on",
    "with",
    "from",
    "using",
    "about",
}

PRACTICAL_HINTS = [
    "rag",
    "agent",
    "workflow",
    "benchmark",
    "evaluation",
    "tool",
    "api",
    "deploy",
    "production",
    "fine-tuning",
    "memory",
    "retrieval",
    "multi-agent",
    "guardrail",
    "observability",
    "latency",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _date_str_from_item(item: dict) -> str:
    ts = _parse_ts(item.get("fetched_at", "")) or _parse_ts(item.get("published", ""))
    if not ts:
        return ""
    return ts.astimezone(timezone.utc).date().isoformat()


def _hours_since_item(item: dict) -> float:
    ts = _parse_ts(item.get("fetched_at", "")) or _parse_ts(item.get("published", ""))
    if not ts:
        return 9999.0
    now = datetime.now(timezone.utc)
    return max(0.0, (now - ts.astimezone(timezone.utc)).total_seconds() / 3600.0)


def _novelty_score(item: dict) -> float:
    h = _hours_since_item(item)
    if h <= 24:
        return 100.0
    if h <= 48:
        return 85.0
    if h <= 72:
        return 70.0
    if h <= 168:
        return 50.0
    return 30.0


def _practicality_score(item: dict) -> float:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    hits = sum(1 for token in PRACTICAL_HINTS if token in text)
    return min(100.0, 35.0 + hits * 15.0)


def _keyword_match_score(item: dict, keywords: list[str]) -> float:
    if not keywords:
        return 40.0
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    hits = 0
    for kw in keywords:
        k = kw.strip().lower()
        if k and k in text:
            hits += 1
    return min(100.0, 20.0 + hits * 25.0)


def _score_item(item: dict, keywords: list[str]) -> tuple[float, dict]:
    novelty = _novelty_score(item)
    practicality = _practicality_score(item)
    keyword_match = _keyword_match_score(item, keywords)
    total = novelty * 0.40 + practicality * 0.35 + keyword_match * 0.25
    return total, {
        "novelty": round(novelty, 1),
        "practicality": round(practicality, 1),
        "keyword_match": round(keyword_match, 1),
    }


def _topic_key(title: str) -> str:
    t = (title or "").lower()
    zh = re.findall(r"[\u4e00-\u9fff]{2,}", t)
    if zh:
        return "".join(zh)[:14]
    en = [w for w in re.findall(r"[a-z0-9\-]{3,}", t) if w not in STOPWORDS_EN]
    return " ".join(en[:5]) or t[:24]


def _summary_3lines(summary: str) -> list[str]:
    text = (summary or "").strip()
    if not text:
        return ["No summary available yet.", "Open source for details.", "Use Search for deep follow-up."]
    parts = [p.strip() for p in re.split(r"[。.!?\n]+", text) if p.strip()]
    out = []
    for p in parts:
        out.append(p[:140])
        if len(out) >= 3:
            break
    while len(out) < 3:
        out.append("...")
    return out


def _is_zh(text: str) -> bool:
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    en_count = len(re.findall(r"[A-Za-z]", text or ""))
    return zh_count > 0 and zh_count >= en_count


def _why_it_matters(item: dict, score_breakdown: dict) -> str:
    title = item.get("title", "")
    if _is_zh(title):
        return (
            f"這則內容在新穎性 {score_breakdown['novelty']} 分，且具有可實作價值，"
            "適合快速建立你今天的 AI 技術視野。"
        )
    return (
        f"This topic scored {score_breakdown['novelty']} on freshness and shows practical implementation value, "
        "so it is a strong daily learning pick."
    )


def _learn_action_15m(item: dict) -> str:
    title = item.get("title", "")
    if _is_zh(title):
        return "花 15 分鐘：先閱讀摘要與原文前兩段，整理 3 個可套用到你專案的做法。"
    return "Spend 15 minutes: read the summary and first two sections, then extract 3 implementation ideas."


def _followup_question(item: dict) -> str:
    title = item.get("title", "")
    if _is_zh(title):
        return f"請用三點說明「{title}」如何應用在 RAG 或 Agent 工作流。"
    return f"Give me 3 practical ways to apply '{title}' in a RAG or agent workflow."


def top3_path(date_str: str) -> Path:
    return RAW_DIR / date_str / "top3.json"


def load_top3(date_str: str) -> dict | None:
    p = top3_path(date_str)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _filter_by_date(items: list[dict], date_str: str) -> list[dict]:
    return [it for it in items if _date_str_from_item(it) == date_str]


def pick_top3(date_str: str, force: bool = False) -> dict:
    """Return cached or freshly selected Daily Learning Top-3 payload."""
    if not force:
        cached = load_top3(date_str)
        if cached:
            return cached

    indexed = list_indexed_items(limit=400)
    day_items = _filter_by_date(indexed, date_str)
    keywords = load_keywords()

    path = top3_path(date_str)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not day_items:
        payload = {
            "date": date_str,
            "picked_at": _now_iso(),
            "model": "heuristic-v1",
            "picks": [],
            "error": f"no indexed items found for {date_str}",
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    scored = []
    for item in day_items:
        score, breakdown = _score_item(item, keywords)
        scored.append((score, breakdown, item))
    scored.sort(key=lambda x: x[0], reverse=True)

    picks: list[dict] = []
    seen_topics: set[str] = set()
    for score, breakdown, item in scored:
        topic = _topic_key(item.get("title", ""))
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        lines = _summary_3lines(item.get("summary", ""))
        pick = {
            "rank": len(picks) + 1,
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "link": item.get("link", ""),
            "published_at": item.get("published", "") or item.get("fetched_at", ""),
            "summary_3lines": lines,
            "why_it_matters": _why_it_matters(item, breakdown),
            "learn_action_15m": _learn_action_15m(item),
            "followup_question": _followup_question(item),
            "score": round(score, 1),
            "score_breakdown": breakdown,
            # backward compatibility field for existing consumers
            "justification": _why_it_matters(item, breakdown),
        }
        picks.append(pick)
        if len(picks) >= 3:
            break

    payload = {
        "date": date_str,
        "picked_at": _now_iso(),
        "model": "heuristic-v1",
        "picks": picks,
    }
    if len(picks) < 3:
        payload["warning"] = f"only {len(picks)} unique topics available for {date_str}"

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def list_all_top3() -> list[dict]:
    out: list[dict] = []
    if not RAW_DIR.exists():
        return out
    for d in sorted([p for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True):
        p = d / "top3.json"
        if not p.exists():
            continue
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
