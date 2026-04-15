"""News page — cached daily top-3 highlights + Atom export + archive search."""
import json
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import RAW_DIR
from src.agents.news_curator import pick_top3, load_top3
from src.agents.news_feed import export_atom

st.title("📰 News — Daily Top 3")

dates = sorted([p.name for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True)
if not dates:
    st.info("No news yet — run the ingest on the Raw Source page.")
    st.stop()

picked_date = st.selectbox("Date", dates)

cached = load_top3(picked_date)
c1, c2 = st.columns([1, 1])
with c1:
    go = st.button("✨ Pick top 3" if not cached else "🔄 Re-pick (force LLM)")
with c2:
    st.caption(
        f"cached: {cached['picked_at']}" if cached else "no cache yet"
    )

if go:
    with st.spinner("Selecting…"):
        payload = pick_top3(picked_date, force=bool(cached))
else:
    payload = cached

if payload and payload.get("picks"):
    st.caption(
        f"picked_at = {payload.get('picked_at','')}  ·  "
        f"model = {payload.get('model','')}"
    )
    for pk in payload["picks"]:
        with st.container(border=True):
            title = pk.get("title", "")
            link = pk.get("link", "")
            rank = pk.get("rank", "?")
            st.markdown(f"**#{rank} — {title}**")
            if link:
                st.markdown(f"[Source]({link})")
            st.write(pk.get("justification", ""))
elif payload and payload.get("error"):
    st.error(payload["error"])
else:
    st.info("No top-3 yet for this date. Click **Pick top 3** above.")

st.divider()
st.subheader("📡 Atom feed export")
st.caption("All cached top-3 picks across every date, newest first.")
if st.button("Generate Atom feed"):
    xml = export_atom(limit=60)
    st.download_button(
        "⬇️ Download atom.xml",
        data=xml.encode("utf-8"),
        file_name="ailearning_top3.atom.xml",
        mime="application/atom+xml",
    )
    with st.expander("Preview XML"):
        st.code(xml, language="xml")

st.divider()
st.subheader("🔎 Archive search")
q = st.text_input("Search past items by keyword")
if q:
    hits = []
    for d in dates:
        pf = RAW_DIR / d / "collected.json"
        if not pf.exists():
            continue
        _p = json.loads(pf.read_text())
        _items = _p.get("items", _p) if isinstance(_p, dict) else _p
        for i in _items:
            if q.lower() in (i.get("title", "") + i.get("summary", "")).lower():
                hits.append((d, i))
    st.caption(f"{len(hits)} matches")
    for d, i in hits[:50]:
        with st.expander(f"[{d}] {i.get('title','')}"):
            st.write(i.get("summary", ""))
            if i.get("link"):
                st.markdown(f"[Source]({i['link']})")
