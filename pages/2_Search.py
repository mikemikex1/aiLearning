"""Search page: friendlier split layout (chat + notes)."""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.agents.search_agent import answer, suggest_prompts
from src.rag.parent_retriever import list_indexed_items
from src.ui.i18n import render_locale_selector, t


def _infer_locale_from_text(text: str, fallback: str) -> str:
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    en_count = len(re.findall(r"[A-Za-z]", text or ""))
    if zh_count >= 2 and zh_count >= en_count:
        return "zh-TW"
    if en_count >= 6 and en_count > zh_count:
        return "en-US"
    return fallback


def _resolve_chat_locale(default_locale: str) -> str:
    chat = st.session_state.get("chat", [])
    for role, msg in reversed(chat):
        if role == "user" and msg.strip():
            return _infer_locale_from_text(msg, default_locale)
    return default_locale


def _indexed_signature(limit: int = 60) -> str:
    items = list_indexed_items(limit=limit)
    key_parts = [
        f"{it.get('link', '')}|{it.get('title', '')}|{it.get('fetched_at', '')}|{it.get('published', '')}"
        for it in items
    ]
    return hashlib.sha1("||".join(key_parts).encode("utf-8")).hexdigest()


def _build_note_markdown(answer_text: str, sources: list[dict], locale: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if locale == "zh-TW":
        lines = [f"# 對話筆記 ({ts})", "", "## 核心重點", answer_text or "(尚無內容)", "", "## 來源清單"]
    else:
        lines = [f"# Conversation Notes ({ts})", "", "## Key Takeaways", answer_text or "(empty)", "", "## Sources"]
    for i, source in enumerate(sources or [], 1):
        lines.append(f"{i}. {source.get('title', '(untitled)')}")
        if source.get("link"):
            lines.append(f"   - {source['link']}")
    return "\n".join(lines)


def _reset_state() -> None:
    st.session_state.chat = []
    st.session_state.last_sources = []
    st.session_state.last_answer = ""
    st.session_state.pending_query = ""
    st.session_state.is_busy = False
    st.session_state.suggestions = []
    st.session_state.suggestions_signature = ""
    st.session_state.note_markdown = ""


locale_setting = render_locale_selector()
chat_locale = _resolve_chat_locale(locale_setting)
L = (lambda zh, en: zh if chat_locale == "zh-TW" else en)

st.title(t("search.title", locale_setting))
st.caption(t("search.caption", locale_setting))

if "chat" not in st.session_state:
    st.session_state.chat = []
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "last_answer" not in st.session_state:
    st.session_state.last_answer = ""
if "pending_query" not in st.session_state:
    st.session_state.pending_query = ""
if "is_busy" not in st.session_state:
    st.session_state.is_busy = False
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []
if "suggestions_signature" not in st.session_state:
    st.session_state.suggestions_signature = ""
if "note_markdown" not in st.session_state:
    st.session_state.note_markdown = ""

current_signature = _indexed_signature()
needs_bootstrap = not st.session_state.suggestions
index_changed = st.session_state.suggestions_signature != current_signature
if (needs_bootstrap or index_changed) and not st.session_state.is_busy:
    st.session_state.suggestions = suggest_prompts(
        query="",
        history=st.session_state.chat,
        locale=chat_locale,
        max_suggestions=3,
    )
    st.session_state.suggestions_signature = current_signature

st.markdown(
    """
<style>
.search-shell { padding: 0.35rem 0.1rem 0.2rem 0.1rem; }
.suggestion-card {
  border: 1px solid rgba(125, 125, 125, 0.25);
  border-radius: 14px;
  padding: 0.55rem 0.6rem 0.35rem 0.6rem;
  margin: 0.35rem 0 0.8rem 0;
  background: linear-gradient(180deg, rgba(220,240,235,0.22), rgba(255,255,255,0.06));
}
.suggestion-card .stButton > button {
  text-align: left; justify-content: flex-start; white-space: normal;
  line-height: 1.35; min-height: 2.4rem; border-radius: 10px; margin-bottom: 0.38rem;
}
.note-card {
  border: 1px solid rgba(100, 130, 120, 0.32);
  border-radius: 16px;
  padding: 0.7rem;
  background: linear-gradient(180deg, rgba(206,236,229,0.18), rgba(255,255,255,0.04));
}
</style>
""",
    unsafe_allow_html=True,
)

ctrl1, ctrl2 = st.columns([1, 7])
with ctrl1:
    if st.button(t("search.reset", chat_locale), disabled=st.session_state.is_busy):
        _reset_state()
        st.rerun()
with ctrl2:
    st.caption(L("左側對話・右側筆記", "Chat on left, notes on right"))

left_col, right_col = st.columns([1.45, 1], gap="large")
selected_suggestion = ""
typed_query = ""

with left_col:
    st.markdown("<div class='search-shell'>", unsafe_allow_html=True)
    for role, msg in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(msg)

    if not st.session_state.is_busy and st.session_state.suggestions:
        st.markdown("<div class='suggestion-card'>", unsafe_allow_html=True)
        st.caption(L("快速建議", "Quick Suggestions"))
        for i, item in enumerate(st.session_state.suggestions[:3], 1):
            if st.button(item, key=f"suggestion_chat_widget_{i}", use_container_width=True):
                selected_suggestion = item
        st.markdown("</div>", unsafe_allow_html=True)

    typed_query = st.chat_input(t("search.input", chat_locale), disabled=st.session_state.is_busy)
    st.markdown("</div>", unsafe_allow_html=True)

prefill_query = ""
if "search_prefill" in st.session_state and not st.session_state.is_busy:
    prefill_query = (st.session_state.pop("search_prefill") or "").strip()

incoming_query = selected_suggestion or prefill_query or (typed_query or "").strip()
if incoming_query and not st.session_state.is_busy:
    st.session_state.pending_query = incoming_query
    st.session_state.suggestions = []
    st.session_state.is_busy = True
    st.rerun()

if st.session_state.is_busy and st.session_state.pending_query:
    user_query = st.session_state.pending_query
    st.session_state.pending_query = ""
    query_locale = _infer_locale_from_text(user_query, chat_locale)

    st.session_state.chat.append(("user", user_query))
    with left_col:
        with st.chat_message("user"):
            st.markdown(user_query)
        with st.chat_message("assistant"):
            with st.spinner(t("search.thinking", query_locale)):
                try:
                    result = answer(user_query, history=st.session_state.chat[:-1], locale=query_locale)
                    assistant_reply = result.get("answer", "")
                    st.session_state.last_sources = result.get("sources", [])
                    st.session_state.last_answer = assistant_reply
                except Exception as exc:  # noqa: BLE001
                    assistant_reply = f"{t('common.error', query_locale)}: {exc}"
                    st.session_state.last_sources = []
                    st.session_state.last_answer = ""
            st.markdown(assistant_reply)

    st.session_state.chat.append(("assistant", assistant_reply))
    st.session_state.suggestions = suggest_prompts(
        query=assistant_reply,
        history=st.session_state.chat,
        locale=query_locale,
        max_suggestions=3,
    )
    st.session_state.suggestions_signature = _indexed_signature()
    st.session_state.note_markdown = _build_note_markdown(assistant_reply, st.session_state.last_sources, query_locale)
    st.session_state.is_busy = False
    st.rerun()

with right_col:
    st.markdown("<div class='note-card'>", unsafe_allow_html=True)
    st.subheader(L("產出筆記", "Generated Notes"))
    st.caption(L("可直接整理、編輯並匯出重點。", "Review, edit, and export notes here."))

    if not st.session_state.last_answer:
        st.info(L("尚無可整理內容，先在左側提問。", "No answer yet. Ask on the left panel first."))
    else:
        regen_col, _ = st.columns([1, 2])
        with regen_col:
            if st.button(L("重新整理筆記", "Regenerate Notes"), use_container_width=True):
                st.session_state.note_markdown = _build_note_markdown(
                    st.session_state.last_answer,
                    st.session_state.last_sources,
                    chat_locale,
                )
                st.rerun()

        edited = st.text_area(L("筆記內容", "Notes"), value=st.session_state.note_markdown, height=420)
        if edited != st.session_state.note_markdown:
            st.session_state.note_markdown = edited

        st.download_button(
            t("search.export.download", chat_locale),
            data=st.session_state.note_markdown.encode("utf-8"),
            file_name="search_notes.md",
            mime="text/markdown",
            use_container_width=True,
        )

        with st.expander(t("search.sources", chat_locale), expanded=False):
            for i, source in enumerate(st.session_state.last_sources, 1):
                icon = "📄" if source.get("source_type") == "project" else "🌐"
                st.markdown(f"**{icon} {source.get('title') or f'source-{i}'}**")
                if source.get("snippet"):
                    st.caption(source["snippet"])
                if source.get("link"):
                    st.markdown(f"[{t('search.open_source', chat_locale)}]({source['link']})")
                st.markdown("---")
    st.markdown("</div>", unsafe_allow_html=True)
