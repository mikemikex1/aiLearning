"""Streamlit entrypoint. Run with: `streamlit run app.py`"""
from __future__ import annotations

import streamlit as st
from src.ui.i18n import render_locale_selector, t

locale = render_locale_selector()

st.set_page_config(page_title=t("app.title", locale), page_icon="📚", layout="wide")

st.title(f"📚 {t('app.title', locale)}")
st.markdown(t("app.desc", locale))

if locale == "zh-TW":
    st.markdown(
        """
- **Settings**：API keys、關鍵字、模型與資料源設定  
- **Search**：對 RAG 與專案知識庫問答  
- **Project**：Planner → Programmer → Tester 流程  
- **Raw Source**：檢視每日抓取資料  
- **News**：每日 Top-3
"""
    )
    st.info("先到 Settings 確認 API key 與語言設定。")
else:
    st.markdown(
        """
- **Settings**: API keys, keywords, models, and source settings  
- **Search**: chat over RAG + indexed project memory  
- **Project**: Planner → Programmer → Tester flow  
- **Raw Source**: browse collected source data  
- **News**: daily top-3 highlights
"""
    )
    st.info("Start from Settings to confirm API key and language.")
