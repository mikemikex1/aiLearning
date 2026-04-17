"""Settings page: API keys, keywords, model routing, source feeds, and locale."""
from __future__ import annotations

import os
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    EMBEDDING_MODEL,
    FEED_CATALOG,
    MODEL_FLASH,
    MODEL_LITE,
    load_keywords,
    load_user_settings,
    save_keywords,
    save_user_settings,
)
from src.ui.i18n import render_locale_selector, t

locale = render_locale_selector()
st.title(t("settings.title", locale))

st.subheader("API Keys")
with st.form("keys"):
    gk = st.text_input("GOOGLE_API_KEY", type="password", value=os.getenv("GOOGLE_API_KEY", ""))
    lk = st.text_input("LANGCHAIN_API_KEY", type="password", value=os.getenv("LANGCHAIN_API_KEY", ""))
    if st.form_submit_button("Save to session"):
        os.environ["GOOGLE_API_KEY"] = gk
        os.environ["LANGCHAIN_API_KEY"] = lk
        st.success(t("settings.saved", locale))

st.divider()
st.subheader("Global Keywords")
kws = load_keywords()
edited = st.text_area("One keyword per line", value="\n".join(kws), height=180)
if st.button("Save global keywords"):
    new = [k.strip() for k in edited.splitlines() if k.strip()]
    save_keywords(new)
    st.success(t("settings.saved", locale))

st.divider()
st.subheader("Model Routing")
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
    "Downgrade complex -> simple on repeated 429",
    value=bool(routing.get("downgrade_on_429", True)),
)
st.info(f"Embedding model: `{EMBEDDING_MODEL}`")

st.divider()
st.subheader("Source Feeds")
feeds_state = dict(settings_data["feeds"])
feed_kw_state = dict(settings_data["feed_keywords"])
for fid, label in FEED_CATALOG.items():
    with st.expander(f"{label} | `{fid}`", expanded=feeds_state.get(fid, True)):
        feeds_state[fid] = st.checkbox("Enabled", value=feeds_state.get(fid, True), key=f"en_{fid}")
        override = st.text_area(
            "Keyword override (one per line, empty = use global)",
            value="\n".join(feed_kw_state.get(fid, [])),
            height=100,
            key=f"kw_{fid}",
        )
        feed_kw_state[fid] = [k.strip() for k in override.splitlines() if k.strip()]

st.divider()
if st.button("Save routing & feeds"):
    settings_data["routing"] = {
        "simple_model": simple_model,
        "complex_model": complex_model,
        "downgrade_on_429": downgrade,
    }
    settings_data["feeds"] = feeds_state
    settings_data["feed_keywords"] = feed_kw_state
    save_user_settings(settings_data)
    st.success(t("settings.saved", locale))
