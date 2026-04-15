"""Settings page — API keys, keywords, model routing, source feeds."""
import os
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    FEED_CATALOG,
    MODEL_LITE,
    MODEL_FLASH,
    load_keywords,
    save_keywords,
    load_user_settings,
    save_user_settings,
)

st.title("⚙️  Settings")

# ---------------- API Keys (masked) ----------------
st.subheader("🔐 API Keys")
with st.form("keys"):
    gk = st.text_input("GOOGLE_API_KEY", type="password",
                       value=os.getenv("GOOGLE_API_KEY", ""))
    lk = st.text_input("LANGCHAIN_API_KEY (LangSmith)", type="password",
                       value=os.getenv("LANGCHAIN_API_KEY", ""))
    if st.form_submit_button("Save to session"):
        os.environ["GOOGLE_API_KEY"] = gk
        os.environ["LANGCHAIN_API_KEY"] = lk
        st.success("Saved for this session. For persistence, edit .env")

st.divider()

# ---------------- Global keywords ----------------
st.subheader("🔑 Global Keywords")
st.caption(
    "Default filter across every enabled source. A per-source override "
    "below (if set) takes precedence for that source."
)
kws = load_keywords()
edited = st.text_area("One keyword per line", value="\n".join(kws),
                      height=180, key="global_kw")
if st.button("Save global keywords"):
    new = [k.strip() for k in edited.splitlines() if k.strip()]
    save_keywords(new)
    st.success(f"Saved {len(new)} keywords")

st.divider()

# ---------------- Model routing ----------------
st.subheader("🧠 Model Routing")
st.caption(
    "Lite = cheap/fast (cleaning, short Q&A). Flash = stronger reasoning "
    "(planning, code, tests, synthesis). Changes apply on the next LLM call."
)

settings_data = load_user_settings()
routing = settings_data["routing"]

model_options = [MODEL_LITE, MODEL_FLASH]

def _safe_idx(val: str, default: int) -> int:
    return model_options.index(val) if val in model_options else default

c1, c2 = st.columns(2)
with c1:
    simple_model = st.selectbox(
        "Simple tasks",
        options=model_options,
        index=_safe_idx(routing.get("simple_model", MODEL_LITE), 0),
    )
with c2:
    complex_model = st.selectbox(
        "Complex tasks",
        options=model_options,
        index=_safe_idx(routing.get("complex_model", MODEL_FLASH), 1),
    )
downgrade = st.checkbox(
    "Downgrade complex → simple on repeated 429 (quota exceeded)",
    value=bool(routing.get("downgrade_on_429", True)),
)

st.divider()

# ---------------- Source feeds + per-source keywords ----------------
st.subheader("📡 Source Feeds")
st.caption(
    "Toggle which sources the Browser Agent fetches. For any feed, you can "
    "set a keyword override (one per line). Empty = inherit global keywords."
)

feeds_state = dict(settings_data["feeds"])
feed_kw_state = dict(settings_data["feed_keywords"])

for fid, label in FEED_CATALOG.items():
    with st.expander(f"{label}  ·  `{fid}`",
                     expanded=feeds_state.get(fid, True)):
        feeds_state[fid] = st.checkbox(
            "Enabled", value=feeds_state.get(fid, True), key=f"en_{fid}"
        )
        override = st.text_area(
            "Keyword override (one per line, empty = use global)",
            value="\n".join(feed_kw_state.get(fid, [])),
            height=100,
            key=f"kw_{fid}",
        )
        feed_kw_state[fid] = [k.strip() for k in override.splitlines()
                              if k.strip()]

# ---------------- Save routing + feeds ----------------
st.divider()
if st.button("💾 Save routing & feeds"):
    settings_data["routing"] = {
        "simple_model": simple_model,
        "complex_model": complex_model,
        "downgrade_on_429": downgrade,
    }
    settings_data["feeds"] = feeds_state
    settings_data["feed_keywords"] = feed_kw_state
    save_user_settings(settings_data)
    st.success("Settings saved. They apply on the next ingest / LLM call.")
