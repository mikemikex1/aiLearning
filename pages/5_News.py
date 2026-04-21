"""News page: Daily Learning Top-3 cards + Atom export + archive search."""
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
st.caption(L("每日學習 3 個 AI 重點", "Daily Learning: 3 AI Highlights"))

dates = sorted([p.name for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True)
if not dates:
    st.info(L("目前沒有資料，請先到 Raw Source 執行 ingest。", "No data yet. Run ingest on Raw Source first."))
    st.stop()

picked_date = st.selectbox(L("日期", "Date"), dates)
cached = load_top3(picked_date)

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    run_pick = st.button(L("重算今日學習 Top 3", "Recompute Daily Top 3"), use_container_width=True)
with c2:
    use_cached = st.button(L("使用快取", "Use Cached"), use_container_width=True, disabled=not bool(cached))
with c3:
    if cached:
        st.caption(f"cached_at: {cached.get('picked_at', '')}")
    else:
        st.caption(L("尚無快取", "no cache yet"))

if run_pick:
    with st.spinner(L("挑選學習重點中...", "Picking learning highlights...")):
        payload = pick_top3(picked_date, force=True)
elif use_cached and cached:
    payload = cached
else:
    payload = cached or pick_top3(picked_date, force=False)

if payload.get("error"):
    st.error(payload["error"])
if payload.get("warning"):
    st.warning(payload["warning"])

picks = payload.get("picks", [])
if picks:
    st.caption(f"picked_at={payload.get('picked_at', '')} | model={payload.get('model', '')}")
    for pick in picks:
        with st.container(border=True):
            rank = pick.get("rank", "?")
            title = pick.get("title", "")
            link = pick.get("link", "")
            source = pick.get("source", "")
            score = pick.get("score", "")
            st.markdown(f"### #{rank} {title}")
            st.caption(f"{source} | score: {score}")

            lines = pick.get("summary_3lines", [])
            if isinstance(lines, list) and lines:
                for line in lines[:3]:
                    st.markdown(f"- {line}")
            else:
                st.write(pick.get("justification", ""))

            st.markdown(f"**{L('為何重要', 'Why It Matters')}**")
            st.write(pick.get("why_it_matters", pick.get("justification", "")))

            st.markdown(f"**{L('15 分鐘學習任務', '15-Min Learning Action')}**")
            st.write(pick.get("learn_action_15m", ""))

            b1, b2 = st.columns([1, 1])
            with b1:
                if link:
                    st.markdown(f"[{L('查看原文', 'Open Source')}]({link})")
            with b2:
                followup = pick.get("followup_question", "")
                if st.button(
                    L("深入問 Search", "Ask in Search"),
                    key=f"ask_{picked_date}_{rank}_{title[:20]}",
                    use_container_width=True,
                    disabled=not bool(followup),
                ):
                    st.session_state["search_prefill"] = followup
                    try:
                        st.switch_page("pages/2_Search.py")
                    except Exception:
                        st.info(L("已準備好問題，請切換到 Search 頁面。", "Question prepared. Please switch to Search page."))

            with st.expander(L("評分細節", "Score Breakdown"), expanded=False):
                st.json(pick.get("score_breakdown", {}))
else:
    st.info(L("這天尚未產生學習 Top-3。", "No Daily Top-3 generated for this date."))

st.divider()
st.subheader(L("Atom 匯出", "Atom Export"))
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
st.subheader(L("歷史搜尋", "Archive Search"))
q = st.text_input(L("用關鍵字搜尋歷史項目", "Search past items by keyword"))
if q:
    hits = []
    ql = q.lower()
    for d in dates:
        pf = RAW_DIR / d / "collected.json"
        if not pf.exists():
            continue
        payload_raw = json.loads(pf.read_text(encoding="utf-8"))
        items = payload_raw.get("items", payload_raw) if isinstance(payload_raw, dict) else payload_raw
        for item in items:
            if ql in (item.get("title", "") + item.get("summary", "")).lower():
                hits.append((d, item))
    st.caption(f"{len(hits)} matches")
    for d, item in hits[:50]:
        with st.expander(f"[{d}] {item.get('title', '')}"):
            st.write(item.get("summary", ""))
            if item.get("link"):
                st.markdown(f"[Source]({item['link']})")
