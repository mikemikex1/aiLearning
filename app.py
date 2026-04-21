"""Streamlit entrypoint. Run with: `streamlit run app.py`."""
from __future__ import annotations

import streamlit as st

from src.ui.i18n import render_locale_selector, t

locale = render_locale_selector()
st.set_page_config(page_title=t("app.title", locale), page_icon="🧠", layout="wide")

st.title(t("app.title", locale))
st.markdown(t("app.desc", locale))

if locale == "zh-TW":
    st.markdown(
        """
- **Settings**：API keys、關鍵字、模型與來源設定
- **Search**：對已索引內容進行問答與筆記整理
- **Raw Source**：檢視抓取原始資料與手動 ingest
- **News**：每日學習 Top-3 與歷史檢索
- **Project（規劃中）**：保留功能敘述，暫不提供可執行頁面
"""
    )
    st.info("建議先到 Settings 確認 API key 與語言。")
else:
    st.markdown(
        """
- **Settings**: API keys, keywords, model routing, and source settings
- **Search**: grounded Q&A and note generation over indexed content
- **Raw Source**: inspect raw collected data and run ingest
- **News**: daily learning Top-3 and archive search
- **Project (Planned)**: feature plan is kept, runtime/page is temporarily removed
"""
    )
    st.info("Start from Settings to confirm API key and language.")
