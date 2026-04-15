"""Streamlit entrypoint. Run with: `streamlit run app.py`"""
import streamlit as st

st.set_page_config(page_title="AI Learning — Phase 1", page_icon="🧠", layout="wide")

st.title("🧠 AI Learning — Phase 1")
st.markdown(
    """
Agentic RAG workflow that turns AI-trend information into **runnable code**.

Use the sidebar to navigate:

- **Settings** — API keys, keyword management
- **Search** — chat over your RAG store + generated projects
- **Project** — pick a topic, run the Planner→Programmer→Tester pipeline
- **Raw Source** — browse raw collected data
- **News** — daily top-3 curated items
"""
)

st.info("👈 Start by opening **Settings** and saving your Gemini API key.")
