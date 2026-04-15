"""Source collectors (Twitter/X alternatives).

Sources
-------
- arXiv cs.AI RSS
- Hacker News front page (Algolia API)
- Hugging Face daily papers
- Simon Willison's blog RSS

Every persisted raw file carries a `description` header and every item
carries a `fetched_at` timestampz (ISO 8601 UTC with Z suffix).
"""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import feedparser
import httpx
from config.settings import RAW_DIR, enabled_feeds, feed_keywords

FEEDS = {
    "arxiv_cs_ai": "http://export.arxiv.org/rss/cs.AI",
    "simonw": "https://simonwillison.net/atom/everything/",
    "hf_papers": "https://huggingface.co/papers/rss",
}
HN_API = "https://hn.algolia.com/api/v1/search?tags=front_page"


def _keyword_match(item: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    blob = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(k.lower() in blob for k in keywords)


def _now_iso() -> str:
    """UTC timestamptz: 2026-04-14T12:34:56.789Z"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _today_dir() -> Path:
    d = RAW_DIR / date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch_rss(name: str, url: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(url)
    now = _now_iso()
    return [
        {"source": name, "title": e.get("title", ""),
         "link": e.get("link", ""), "summary": e.get("summary", ""),
         "published": e.get("published", ""),
         "fetched_at": now}
        for e in parsed.entries[:30]
    ]


def fetch_hn() -> list[dict[str, Any]]:
    try:
        r = httpx.get(HN_API, timeout=15.0)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        now = _now_iso()
        return [{"source": "hn", "title": h.get("title", ""),
                 "link": h.get("url", ""),
                 "summary": h.get("story_text", "") or "",
                 "published": h.get("created_at", ""),
                 "fetched_at": now} for h in hits]
    except Exception:
        return []


def collect_all(keywords: list[str] | None = None) -> Path:
    """Fetch all *enabled* sources and persist as raw JSON under data/raw/<date>/.

    Respects Settings-page toggles and per-source keyword overrides:
      - A source is skipped entirely if its toggle is off in user_settings.json
      - If the source has a non-empty feed_keywords override, that list is used
        instead of the global `keywords` arg for filtering items from that source.

    The file is wrapped with a `description` header containing the
    fetched_at timestampz; each item also carries its own `fetched_at`.
    A timestamped filename is written alongside a stable `collected.json`
    pointer for the latest run of the day.
    """
    enabled = enabled_feeds()
    raw_per_source: dict[str, list[dict]] = {}

    for name, url in FEEDS.items():
        if not enabled.get(name, True):
            continue
        raw_per_source[name] = fetch_rss(name, url)

    if enabled.get("hn", True):
        raw_per_source["hn"] = fetch_hn()

    # Per-source filtering: override list beats the global `keywords` arg.
    items: list[dict] = []
    for src, src_items in raw_per_source.items():
        overrides = feed_keywords(src)
        effective = overrides if overrides else (keywords or [])
        items.extend(i for i in src_items if _keyword_match(i, effective))

    now = _now_iso()
    sources_used = sorted(raw_per_source.keys())
    payload = {
        "description": (
            f"AILearning daily fetch — fetched_at={now} "
            f"sources=[{', '.join(sources_used)}]"
        ),
        "fetched_at": now,
        "keywords": keywords or [],
        "source_count": len({i["source"] for i in items}),
        "item_count": len(items),
        "items": items,
    }
    safe = now.replace(":", "").replace("-", "").replace(".", "")
    out = _today_dir() / f"collected_{safe}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (out.parent / "collected.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2))
    return out
