"""Atom 1.0 feed exporter over persisted top-3 picks."""
from __future__ import annotations
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from src.agents.news_curator import list_all_top3


FEED_ID = "tag:ailearning.local,2026:top3"
FEED_TITLE = "AI Learning — Daily Top 3"
FEED_AUTHOR = "AI Learning"


def _atom_time(iso: str) -> str:
    # Normalise to Atom-compliant RFC 3339
    if not iso:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return iso.replace("+00:00", "Z")


def export_atom(limit: int = 30) -> str:
    payloads = list_all_top3()[:limit]
    updated = _atom_time(payloads[0]["picked_at"]) if payloads else _atom_time("")

    entries_xml: list[str] = []
    for pl in payloads:
        date = pl.get("date", "")
        picked_at = _atom_time(pl.get("picked_at", ""))
        for pick in pl.get("picks", []):
            rank = pick.get("rank", "?")
            title = escape(f"[{date} #{rank}] {pick.get('title', '')}")
            link = escape(pick.get("link", "") or "")
            justification = escape(pick.get("justification", ""))
            entry_id = f"{FEED_ID}:{date}:{rank}"
            entries_xml.append(
                "<entry>"
                f"<id>{entry_id}</id>"
                f"<title>{title}</title>"
                f'<link rel="alternate" href="{link}"/>'
                f"<updated>{picked_at}</updated>"
                f"<summary>{justification}</summary>"
                "</entry>"
            )

    body = "\n".join(entries_xml)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"<id>{FEED_ID}</id>\n"
        f"<title>{escape(FEED_TITLE)}</title>\n"
        f"<updated>{updated}</updated>\n"
        f"<author><name>{escape(FEED_AUTHOR)}</name></author>\n"
        f"{body}\n"
        "</feed>\n"
    )
