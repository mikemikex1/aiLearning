"""Search page — chat over RAG + indexed projects, with memory."""
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.agents.search_agent import answer

st.title("🔎 Search")
st.caption("Project-aware RAG chat. Conversation memory is kept for this session.")

if "chat" not in st.session_state:
    st.session_state.chat = []  # list of (role, content)
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []

col_ctl, _ = st.columns([1, 5])
with col_ctl:
    if st.button("🗑️  Reset"):
        st.session_state.chat = []
        st.session_state.last_sources = []
        st.rerun()

# Render history
for role, msg in st.session_state.chat:
    with st.chat_message(role):
        st.markdown(msg)

q = st.chat_input("Ask a question…")
if q:
    st.session_state.chat.append(("user", q))
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                res = answer(q, history=st.session_state.chat[:-1])
                reply = res["answer"]
                st.session_state.last_sources = res.get("sources", [])
            except Exception as e:  # noqa: BLE001
                reply = f"Error: {e}"
                st.session_state.last_sources = []
        st.markdown(reply)
    st.session_state.chat.append(("assistant", reply))

# Richer citations panel
if st.session_state.last_sources:
    st.divider()
    st.subheader("📚 Sources used in last answer")
    for i, s in enumerate(st.session_state.last_sources, 1):
        icon = "🧩" if s.get("source_type") == "project" else "🌐"
        title = s.get("title") or f"source-{i}"
        header = f"{icon} [{i}] {title}"
        if s.get("kind"):
            header += f" · `{s['kind']}`"
        if s.get("file"):
            header += f" · `{s['file']}`"
        with st.expander(header):
            if s.get("snippet"):
                st.caption(s["snippet"] + "…")
            if s.get("link"):
                st.markdown(f"[Open source]({s['link']})")
