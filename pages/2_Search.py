"""Search page: aligned chat + notes with inline send/stop controls."""
from __future__ import annotations

import hashlib
import re
import sys
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.agents.search_agent import answer, suggest_prompts
from src.rag.parent_retriever import list_indexed_items
from src.ui.i18n import render_locale_selector, t

_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _infer_locale_from_text(text: str, fallback: str) -> str:
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    en_count = len(re.findall(r"[A-Za-z]", text or ""))
    if zh_count >= 2 and zh_count >= en_count:
        return "zh-TW"
    if en_count >= 6 and en_count > zh_count:
        return "en-US"
    return fallback


def _resolve_chat_locale(default_locale: str) -> str:
    for role, msg in reversed(st.session_state.get("chat", [])):
        if role == "user" and msg.strip():
            return _infer_locale_from_text(msg, default_locale)
    return default_locale


def _indexed_signature(limit: int = 60) -> str:
    items = list_indexed_items(limit=limit)
    raw = "||".join(
        f"{it.get('link', '')}|{it.get('title', '')}|{it.get('fetched_at', '')}|{it.get('published', '')}"
        for it in items
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


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


def _init_state() -> None:
    defaults = {
        "chat": [],
        "last_sources": [],
        "last_answer": "",
        "is_busy": False,
        "suggestions": [],
        "suggestions_signature": "",
        "note_markdown": "",
        "active_future": None,
        "active_job_id": "",
        "active_query_locale": "zh-TW",
        "active_user_query": "",
        "canceled_jobs": [],
        "search_input_text": "",
        "clear_input_next": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _start_async_reply(query: str, history: list[tuple[str, str]], locale: str) -> tuple[str, Future]:
    return str(uuid.uuid4()), _EXECUTOR.submit(answer, query, history=history, locale=locale)


def _finalize_busy_job() -> None:
    if not st.session_state.is_busy:
        return
    future = st.session_state.active_future
    if future is None:
        st.session_state.is_busy = False
        return
    if not future.done():
        return

    job_id = st.session_state.active_job_id
    if job_id in st.session_state.canceled_jobs:
        st.session_state.canceled_jobs = [x for x in st.session_state.canceled_jobs if x != job_id]
    else:
        query_locale = st.session_state.active_query_locale or "zh-TW"
        try:
            result = future.result()
            assistant_reply = result.get("answer", "")
            st.session_state.last_sources = result.get("sources", [])
            st.session_state.last_answer = assistant_reply
        except Exception as exc:  # noqa: BLE001
            assistant_reply = f"{t('common.error', query_locale)}: {exc}"
            st.session_state.last_sources = []
            st.session_state.last_answer = ""

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
    st.session_state.active_future = None
    st.session_state.active_job_id = ""
    st.session_state.active_user_query = ""


def _stop_current_job(chat_locale: str) -> None:
    if st.session_state.active_job_id:
        st.session_state.canceled_jobs.append(st.session_state.active_job_id)
    st.session_state.is_busy = False
    st.session_state.active_future = None
    st.session_state.active_job_id = ""
    st.session_state.active_user_query = ""
    st.session_state.suggestions = suggest_prompts(
        query="",
        history=st.session_state.chat,
        locale=chat_locale,
        max_suggestions=3,
    )


locale_setting = render_locale_selector()
_init_state()
_finalize_busy_job()
chat_locale = _resolve_chat_locale(locale_setting)
L = (lambda zh, en: zh if chat_locale == "zh-TW" else en)

st.title(t("search.title", locale_setting))
st.caption(t("search.caption", locale_setting))

sig = _indexed_signature()
if (not st.session_state.suggestions or st.session_state.suggestions_signature != sig) and not st.session_state.is_busy:
    st.session_state.suggestions = suggest_prompts(
        query="",
        history=st.session_state.chat,
        locale=chat_locale,
        max_suggestions=3,
    )
    st.session_state.suggestions_signature = sig

st.markdown(
    """
<style>
.pane {
  min-height: 62vh;
}
.note-card {
  border: 1px solid rgba(100, 130, 120, 0.32);
  border-radius: 16px;
  padding: 0.7rem;
  min-height: 62vh;
  background: linear-gradient(180deg, rgba(206,236,229,0.18), rgba(255,255,255,0.04));
}
.suggestion-card {
  border: 1px solid rgba(125, 125, 125, 0.25);
  border-radius: 14px;
  padding: 0.55rem 0.6rem 0.35rem 0.6rem;
  margin: 0.35rem 0 0.8rem 0;
  background: linear-gradient(180deg, rgba(220,240,235,0.22), rgba(255,255,255,0.06));
}
.suggestion-card .stButton > button {
  text-align: left;
  justify-content: flex-start;
  white-space: normal;
  line-height: 1.35;
  min-height: 2.3rem;
  border-radius: 10px;
  margin-bottom: 0.35rem;
}
div[data-testid="stChatMessageContent"], .stMarkdown, .stTextArea {
  overflow-wrap: anywhere;
  word-break: break-word;
}
</style>
""",
    unsafe_allow_html=True,
)

left_col, right_col = st.columns([1.45, 1], gap="large")
selected_suggestion = ""
send_clicked = False
stop_clicked = False
refresh_clicked = False

with left_col:
    st.markdown("<div class='pane'>", unsafe_allow_html=True)
    for role, msg in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(msg)

    if st.session_state.is_busy:
        with st.chat_message("assistant"):
            st.info(L("正在產生回覆...", "Generating response..."))
    elif st.session_state.suggestions:
        st.markdown("<div class='suggestion-card'>", unsafe_allow_html=True)
        st.caption(L("快速建議", "Quick Suggestions"))
        for i, item in enumerate(st.session_state.suggestions[:3], 1):
            if st.button(item, key=f"suggestion_chat_widget_{i}", use_container_width=True):
                selected_suggestion = item
        st.markdown("</div>", unsafe_allow_html=True)

    prefill_query = ""
    if "search_prefill" in st.session_state and not st.session_state.is_busy:
        prefill_query = (st.session_state.pop("search_prefill") or "").strip()

    c_input, c_send, c_stop, c_refresh = st.columns([9, 1.2, 1.2, 1.2], gap="small")
    with c_input:
        if st.session_state.clear_input_next:
            st.session_state.search_input_text = ""
            st.session_state.clear_input_next = False
        st.text_input(
            "",
            key="search_input_text",
            placeholder=t("search.input", chat_locale),
            label_visibility="collapsed",
            disabled=st.session_state.is_busy,
        )
    with c_send:
        send_clicked = st.button(L("送出", "Send"), use_container_width=True, disabled=st.session_state.is_busy)
    with c_stop:
        stop_clicked = st.button(L("停止", "Stop"), use_container_width=True, disabled=not st.session_state.is_busy)
    with c_refresh:
        refresh_clicked = st.button(L("更新", "Refresh"), use_container_width=True, disabled=not st.session_state.is_busy)
    st.markdown("</div>", unsafe_allow_html=True)

if stop_clicked and st.session_state.is_busy:
    _stop_current_job(chat_locale)
    st.rerun()
if refresh_clicked and st.session_state.is_busy:
    st.rerun()

incoming_query = selected_suggestion or prefill_query
if not incoming_query and send_clicked and not st.session_state.is_busy:
    incoming_query = (st.session_state.search_input_text or "").strip()

if incoming_query and not st.session_state.is_busy:
    query_locale = _infer_locale_from_text(incoming_query, chat_locale)
    st.session_state.chat.append(("user", incoming_query))
    st.session_state.clear_input_next = True
    job_id, future = _start_async_reply(incoming_query, st.session_state.chat[:-1], query_locale)
    st.session_state.active_future = future
    st.session_state.active_job_id = job_id
    st.session_state.active_user_query = incoming_query
    st.session_state.active_query_locale = query_locale
    st.session_state.suggestions = []
    st.session_state.is_busy = True
    st.rerun()

with right_col:
    st.markdown("<div class='note-card'>", unsafe_allow_html=True)
    st.subheader(L("產出筆記", "Generated Notes"))
    st.caption(L("可直接整理、編輯並匯出重點。", "Review, edit, and export notes here."))

    if not st.session_state.last_answer:
        st.info(L("尚無可整理內容，先在左側提問。", "No answer yet. Ask on the left panel first."))
    else:
        if st.button(L("重新整理筆記", "Regenerate Notes"), use_container_width=True):
            st.session_state.note_markdown = _build_note_markdown(
                st.session_state.last_answer,
                st.session_state.last_sources,
                chat_locale,
            )
            st.rerun()

        edited = st.text_area(
            L("筆記內容", "Notes"),
            value=st.session_state.note_markdown,
            height=420,
        )
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
