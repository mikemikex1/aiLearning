"""Search page: chat over RAG + quick suggestions + localized export preview."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.agents.search_agent import answer, suggest_prompts
from src.ui.i18n import render_locale_selector, t

locale = render_locale_selector()

st.title(t("search.title", locale))
st.caption(t("search.caption", locale))

if "chat" not in st.session_state:
    st.session_state.chat = []
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "last_answer" not in st.session_state:
    st.session_state.last_answer = ""
if "pending_query" not in st.session_state:
    st.session_state.pending_query = ""

col_ctl, _ = st.columns([1, 5])
with col_ctl:
    if st.button(t("search.reset", locale)):
        st.session_state.chat = []
        st.session_state.last_sources = []
        st.session_state.last_answer = ""
        st.session_state.pending_query = ""
        st.rerun()

st.markdown(
    """
<style>
div[data-testid="stButton"] > button {
  text-align: left;
  justify-content: flex-start;
  white-space: normal;
  line-height: 1.35;
  min-height: 3rem;
}
</style>
""",
    unsafe_allow_html=True,
)

left_col, right_col = st.columns([1.35, 4], gap="large")

with left_col:
    st.subheader(t("search.suggestions", locale))
    suggestions = suggest_prompts(
        query=st.session_state.pending_query,
        history=st.session_state.chat,
        locale=locale,
        max_suggestions=3,
    )
    if len(suggestions) < 3:
        fallback = (
            [
                "請用三點整理今天最值得關注的 AI 文章",
                "這篇 RAG 與 Agent 結合方案的重點是什麼？",
                "請比較最近兩篇與 Agent 可靠性相關的文章",
            ]
            if locale == "zh-TW"
            else [
                "Summarize today's top AI articles in 3 points.",
                "What is the key idea of this RAG + Agent solution?",
                "Compare two recent articles about agent reliability.",
            ]
        )
        for item in fallback:
            if item not in suggestions:
                suggestions.append(item)
            if len(suggestions) >= 3:
                break

    if suggestions:
        for i, s in enumerate(suggestions[:3], 1):
            if st.button(s, key=f"suggest_left_{i}", use_container_width=True):
                st.session_state.pending_query = s
                st.rerun()
            if i < 3:
                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    else:
        st.caption(t("search.suggest.none", locale))

with right_col:
    # Render history
    for role, msg in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(msg)

    q = st.chat_input(t("search.input", locale))
    if st.session_state.pending_query:
        q = st.session_state.pending_query
        st.session_state.pending_query = ""

    if q:
        st.session_state.chat.append(("user", q))
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner(t("search.thinking", locale)):
                try:
                    res = answer(q, history=st.session_state.chat[:-1], locale=locale)
                    reply = res["answer"]
                    st.session_state.last_sources = res.get("sources", [])
                    st.session_state.last_answer = reply
                except Exception as e:  # noqa: BLE001
                    reply = f"{t('common.error', locale)}: {e}"
                    st.session_state.last_sources = []
                    st.session_state.last_answer = ""
            st.markdown(reply)
        st.session_state.chat.append(("assistant", reply))

    if st.session_state.last_sources:
        st.divider()
        st.subheader(t("search.sources", locale))
        for i, s in enumerate(st.session_state.last_sources, 1):
            icon = "🧩" if s.get("source_type") == "project" else "🌐"
            title = s.get("title") or f"source-{i}"
            header = f"{icon} [{i}] {title}"
            if s.get("kind"):
                header += f" | `{s['kind']}`"
            if s.get("file"):
                header += f" | `{s['file']}`"
            with st.expander(header):
                if s.get("snippet"):
                    st.caption(s["snippet"] + "...")
                if s.get("link"):
                    st.markdown(f"[{t('search.open_source', locale)}]({s['link']})")
                if s.get("parent_text"):
                    with st.expander(t("search.full_chunk", locale)):
                        st.text(s["parent_text"])

    st.divider()
    st.subheader(t("search.export", locale))
    st.caption(t("search.export.caption", locale))
    if not st.session_state.last_answer:
        st.info(t("search.export.empty", locale))
    else:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if locale == "zh-TW":
            lines = [
                f"# Search 匯出預覽 ({ts})",
                "",
                "## 最新回答",
                st.session_state.last_answer,
                "",
                "## 引用來源",
            ]
            for i, s in enumerate(st.session_state.last_sources, 1):
                lines.append(f"{i}. {s.get('title','(無標題)')}")
                if s.get("link"):
                    lines.append(f"   - {s['link']}")
        else:
            lines = [
                f"# Search Export Preview ({ts})",
                "",
                "## Latest Answer",
                st.session_state.last_answer,
                "",
                "## Sources",
            ]
            for i, s in enumerate(st.session_state.last_sources, 1):
                lines.append(f"{i}. {s.get('title','(untitled)')}")
                if s.get("link"):
                    lines.append(f"   - {s['link']}")
        md = "\n".join(lines)
        st.markdown(md)
        st.download_button(
            t("search.export.download", locale),
            data=md.encode("utf-8"),
            file_name="search_preview.md",
            mime="text/markdown",
        )
