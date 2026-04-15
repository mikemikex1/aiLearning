"""Raw Source page — browse the data/raw/ archive."""
import json
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import RAW_DIR
from src.agents.browser_rag import run_daily_ingest

st.title("📦 Raw Source")

if st.button("🔄 Run daily ingest now"):
    with st.spinner("Fetching sources, cleaning, embedding…"):
        try:
            summary = run_daily_ingest()
            st.success(summary)
        except Exception as e:  # noqa: BLE001
            st.error(str(e))

st.divider()
dates = sorted([p.name for p in RAW_DIR.iterdir() if p.is_dir()], reverse=True)
if not dates:
    st.info("No raw data yet — run the daily ingest above.")
else:
    picked = st.selectbox("Date", dates)
    q = st.text_input("Filter by keyword")
    files = list((RAW_DIR / picked).glob("*.json"))
    for f in files:
        payload = json.loads(f.read_text())
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        desc = payload.get("description", "") if isinstance(payload, dict) else ""
        if q:
            items = [i for i in items if q.lower() in (i.get("title", "") + i.get("summary", "")).lower()]
        st.caption(f"{f.name} — {len(items)} items  ·  {desc}")
        for it in items[:50]:
            with st.expander(it.get("title", "(no title)")):
                st.write(it.get("summary", ""))
                if it.get("link"):
                    st.markdown(f"[Source]({it['link']})")
