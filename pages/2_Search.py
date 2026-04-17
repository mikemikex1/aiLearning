"""Search page: chat over indexed RAG with in-chat suggestions."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.agents.search_agent import answer, suggest_prompts
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


def _reset_state() -> None:
    st.session_state.chat = []
    st.session_state.last_sources = []
    st.session_state.last_answer = ""
    st.session_state.pending_query = ""
    st.session_state.is_busy = False
    st.session_state.suggestions = []


locale_setting = render_locale_selector()
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

if not st.session_state.suggestions:
    boot_locale = _resolve_chat_locale(locale_setting)
    st.session_state.suggestions = suggest_prompts(
        query="",
        history=st.session_state.chat,
        locale=boot_locale,
        max_suggestions=3,
    )

control_col, _ = st.columns([1, 6])
with control_col:
    if st.button(t("search.reset", locale_setting), disabled=st.session_state.is_busy):
        _reset_state()
        st.rerun()

st.markdown(
    """
<style>
.suggestion-wrap {
  margin: 0.2rem 0 0.9rem 0;
}
.suggestion-wrap .stButton > button {
  text-align: left;
  justify-content: flex-start;
  line-height: 1.35;
  white-space: normal;
  min-height: 2.5rem;
  margin-bottom: 0.45rem;
  border-radius: 12px;
}
</style>
""",
    unsafe_allow_html=True,
)

for role, msg in st.session_state.chat:
    with st.chat_message(role):
        st.markdown(msg)

chat_locale = _resolve_chat_locale(locale_setting)
selected_suggestion = ""
if not st.session_state.is_busy and st.session_state.suggestions:
    st.markdown("<div class='suggestion-wrap'>", unsafe_allow_html=True)
    for i, item in enumerate(st.session_state.suggestions[:3], 1):
        if st.button(item, key=f"suggestion_in_chat_{i}", use_container_width=True):
            selected_suggestion = item
    st.markdown("</div>", unsafe_allow_html=True)

typed_query = st.chat_input(t("search.input", chat_locale), disabled=st.session_state.is_busy)
incoming_query = selected_suggestion or (typed_query or "").strip()
if incoming_query and not st.session_state.is_busy:
    st.session_state.pending_query = incoming_query
    st.session_state.suggestions = []
    st.session_state.is_busy = True
    st.rerun()

if st.session_state.is_busy and st.session_state.pending_query:
    user_query = st.session_state.pending_query
    st.session_state.pending_query = ""

    st.session_state.chat.append(("user", user_query))
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner(t("search.thinking", chat_locale)):
            try:
                result = answer(
                    user_query,
                    history=st.session_state.chat[:-1],
                    locale=_infer_locale_from_text(user_query, chat_locale),
                )
                assistant_reply = result.get("answer", "")
                st.session_state.last_sources = result.get("sources", [])
                st.session_state.last_answer = assistant_reply
            except Exception as exc:  # noqa: BLE001
                assistant_reply = f"{t('common.error', chat_locale)}: {exc}"
                st.session_state.last_sources = []
                st.session_state.last_answer = ""
        st.markdown(assistant_reply)

    st.session_state.chat.append(("assistant", assistant_reply))
    st.session_state.suggestions = suggest_prompts(
        query=assistant_reply,
        history=st.session_state.chat,
        locale=_resolve_chat_locale(locale_setting),
        max_suggestions=3,
    )
    st.session_state.is_busy = False
    st.rerun()

if st.session_state.last_sources:
    with st.expander(t("search.sources", chat_locale), expanded=False):
        for i, source in enumerate(st.session_state.last_sources, 1):
            title = source.get("title") or f"source-{i}"
            link = source.get("link", "")
            source_type = source.get("source_type", "web")
            icon = "📄" if source_type == "project" else "🌐"
            st.markdown(f"**{icon} {title}**")
            snippet = source.get("snippet", "")
            if snippet:
                st.caption(snippet)
            if link:
                st.markdown(f"[{t('search.open_source', chat_locale)}]({link})")
            st.markdown("---")

with st.expander(t("search.export", chat_locale), expanded=False):
    st.caption(t("search.export.caption", chat_locale))
    if not st.session_state.last_answer:
        st.info(t("search.export.empty", chat_locale))
    else:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if chat_locale == "zh-TW":
            lines = [
                f"# Search 匯出預覽 ({ts})",
                "",
                "## 最新回答",
                st.session_state.last_answer,
                "",
                "## 來源",
            ]
        else:
            lines = [
                f"# Search Export Preview ({ts})",
                "",
                "## Latest Answer",
                st.session_state.last_answer,
                "",
                "## Sources",
            ]
        for i, source in enumerate(st.session_state.last_sources, 1):
            title = source.get("title", "(untitled)")
            lines.append(f"{i}. {title}")
            if source.get("link"):
                lines.append(f"   - {source['link']}")
        markdown = "\n".join(lines)
        st.markdown(markdown)
        st.download_button(
            t("search.export.download", chat_locale),
            data=markdown.encode("utf-8"),
            file_name="search_preview.md",
            mime="text/markdown",
        )
