"""Raw Source page: browse data/raw and trigger ingest."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import RAW_DIR
from src.agents.browser_rag import run_daily_ingest
from src.ui.i18n import render_locale_selector, t

locale = render_locale_selector()
L = (lambda zh, en: zh if locale == "zh-TW" else en)

st.title(t("raw.title", locale))

if st.button(L("立即執行每日 ingest", "Run daily ingest now")):
    with st.spinner(L("抓取來源、清洗、入庫中...", "Fetching sources, cleaning, embedding...")):
        try:
            summary = run_daily_ingest()
            st.success(summary)
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

st.divider()
dates = sorted([p.name for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True)
if not dates:
    st.info(L("目前沒有 raw 資料，請先執行 ingest。", "No raw data yet. Run ingest first."))
else:
    picked = st.selectbox(L("日期", "Date"), dates)
    q = st.text_input(L("關鍵字過濾", "Filter by keyword"))
    files = sorted((RAW_DIR / picked).glob("collected_*.json"), reverse=True)
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        desc = payload.get("description", "") if isinstance(payload, dict) else ""
        if q:
            ql = q.lower()
            items = [i for i in items if ql in (i.get("title", "") + i.get("summary", "")).lower()]
        st.caption(f"{f.name} | {len(items)} items | {desc}")
        for it in items[:50]:
            with st.expander(it.get("title", "(no title)")):
                st.write(it.get("summary", ""))
                if it.get("link"):
                    st.markdown(f"[Source]({it['link']})")
