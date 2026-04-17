"""News page: daily top-3 highlights + Atom export + archive search."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import RAW_DIR
from src.agents.news_curator import load_top3, pick_top3
from src.agents.news_feed import export_atom
from src.ui.i18n import render_locale_selector, t

locale = render_locale_selector()
L = (lambda zh, en: zh if locale == "zh-TW" else en)

st.title(t("news.title", locale))

dates = sorted([p.name for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True)
if not dates:
    st.info(L("尚無新聞資料，請先在 Raw Source 執行 ingest。", "No news yet. Run ingest on Raw Source first."))
    st.stop()

picked_date = st.selectbox(L("日期", "Date"), dates)
cached = load_top3(picked_date)

c1, c2 = st.columns([1, 1])
with c1:
    go = st.button(L("重選 Top 3（使用 LLM）", "Pick top 3"))
with c2:
    st.caption(f"cached: {cached['picked_at']}" if cached else L("尚無快取", "no cache yet"))

if go:
    with st.spinner(L("挑選中...", "Selecting...")):
        payload = pick_top3(picked_date, force=True)
else:
    payload = cached

if payload and payload.get("picks"):
    st.caption(f"picked_at={payload.get('picked_at','')} | model={payload.get('model','')}")
    for pk in payload["picks"]:
        with st.container(border=True):
            title = pk.get("title", "")
            link = pk.get("link", "")
            rank = pk.get("rank", "?")
            st.markdown(f"**#{rank} {title}**")
            if link:
                st.markdown(f"[Source]({link})")
            st.write(pk.get("justification", ""))
elif payload and payload.get("error"):
    st.error(payload["error"])
else:
    st.info(L("此日期尚無 Top-3。", "No top-3 yet for this date."))

st.divider()
st.subheader(L("Atom 匯出", "Atom export"))
if st.button(L("產生 Atom feed", "Generate Atom feed")):
    xml = export_atom(limit=60)
    st.download_button(
        L("下載 atom.xml", "Download atom.xml"),
        data=xml.encode("utf-8"),
        file_name="ailearning_top3.atom.xml",
        mime="application/atom+xml",
    )
    with st.expander("Preview XML"):
        st.code(xml, language="xml")

st.divider()
st.subheader(L("歷史搜尋", "Archive search"))
q = st.text_input(L("用關鍵字搜尋過往項目", "Search past items by keyword"))
if q:
    hits = []
    ql = q.lower()
    for d in dates:
        pf = RAW_DIR / d / "collected.json"
        if not pf.exists():
            continue
        payload = json.loads(pf.read_text(encoding="utf-8"))
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        for i in items:
            if ql in (i.get("title", "") + i.get("summary", "")).lower():
                hits.append((d, i))
    st.caption(f"{len(hits)} matches")
    for d, i in hits[:50]:
        with st.expander(f"[{d}] {i.get('title','')}"):
            st.write(i.get("summary", ""))
            if i.get("link"):
                st.markdown(f"[Source]({i['link']})")
