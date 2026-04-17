"""Simple i18n helpers for Streamlit pages."""
from __future__ import annotations

import streamlit as st

from config.settings import get_locale, set_locale

_I18N = {
    "zh-TW": {
        "lang.label": "語言",
        "lang.zh": "繁體中文",
        "lang.en": "English",
        "app.title": "AI Learning | Phase 1",
        "app.desc": "Agentic RAG 工作流：每日抓取、檢索、問答與輸出。",
        "search.title": "對話",
        "search.caption": "可直接對已索引的 RAG 內容提問。",
        "search.reset": "重設對話",
        "search.input": "開始輸入...",
        "search.thinking": "思考中...",
        "search.suggestions": "建議問題",
        "search.sources": "本次回答來源",
        "search.open_source": "開啟來源",
        "search.full_chunk": "顯示完整內容片段",
        "search.export": "匯出預覽",
        "search.export.caption": "依目前語言產生摘要並下載。",
        "search.export.download": "下載預覽 (Markdown)",
        "search.export.empty": "目前尚無可匯出內容。",
        "search.suggest.none": "目前沒有建議題目，請先提出問題。",
        "settings.title": "設定",
        "settings.saved": "已儲存。",
        "raw.title": "Raw Source",
        "news.title": "News",
        "project.title": "Project",
        "common.error": "錯誤",
    },
    "en-US": {
        "lang.label": "Language",
        "lang.zh": "Traditional Chinese",
        "lang.en": "English",
        "app.title": "AI Learning | Phase 1",
        "app.desc": "Agentic RAG workflow for daily collection, retrieval, and outputs.",
        "search.title": "Chat",
        "search.caption": "Ask questions over indexed RAG content.",
        "search.reset": "Reset Chat",
        "search.input": "Start typing...",
        "search.thinking": "Thinking...",
        "search.suggestions": "Suggested Questions",
        "search.sources": "Sources",
        "search.open_source": "Open source",
        "search.full_chunk": "Show full context chunk",
        "search.export": "Export Preview",
        "search.export.caption": "Generate a preview in current language and download it.",
        "search.export.download": "Download preview (Markdown)",
        "search.export.empty": "Nothing to export yet.",
        "search.suggest.none": "No suggestion yet. Ask a question first.",
        "settings.title": "Settings",
        "settings.saved": "Saved.",
        "raw.title": "Raw Source",
        "news.title": "News",
        "project.title": "Project",
        "common.error": "Error",
    },
}


def t(key: str, locale: str | None = None) -> str:
    lc = locale or get_locale()
    return _I18N.get(lc, _I18N["zh-TW"]).get(key, key)


def render_locale_selector() -> str:
    """Render global locale selector in sidebar and persist to settings."""
    current = get_locale()
    options = ["zh-TW", "en-US"]
    labels = {"zh-TW": t("lang.zh", current), "en-US": t("lang.en", current)}
    choice = st.sidebar.selectbox(
        t("lang.label", current),
        options=options,
        index=options.index(current),
        format_func=lambda x: labels[x],
        key="global_locale_select",
    )
    if choice != current:
        set_locale(choice)
        st.rerun()
    return choice
