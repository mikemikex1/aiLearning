"""Central configuration. Reads from env + JSON stores under config/."""
from __future__ import annotations
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _sanitize_broken_proxy_env() -> None:
    """Clear known-bad loopback proxy values that break cloud model calls."""
    bad_values = {
        "http://127.0.0.1:9",
        "http://localhost:9",
        "127.0.0.1:9",
        "localhost:9",
    }
    keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "GIT_HTTP_PROXY",
        "GIT_HTTPS_PROXY",
    ]
    for k in keys:
        v = os.getenv(k, "").strip()
        if v and v.lower() in bad_values:
            os.environ.pop(k, None)


_sanitize_broken_proxy_env()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"
LOG_DIR = DATA_DIR / "logs"
HF_CACHE_DIR = DATA_DIR / "hf_cache"
KEYWORDS_FILE = ROOT / "config" / "keywords.json"
USER_SETTINGS_FILE = ROOT / "config" / "user_settings.json"

for d in (RAW_DIR, CHROMA_DIR, LOG_DIR, HF_CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Keep model/cache writes inside project to avoid user-profile permission issues.
os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_CACHE_DIR / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_CACHE_DIR / "transformers"))

# ---- Verified Gemini free-tier models (April 2026) ----
MODEL_LITE = "gemini-2.5-flash-lite"   # 15 RPM · 1000 RPD
MODEL_FLASH = "gemini-2.5-flash"       # 10 RPM · 250 RPD
# NOTE:
# - text-embedding-004 is not available on current Gemini API v1beta for this key.
# - gemini-embedding-001 is currently supported for embed_content.
EMBEDDING_MODEL = "gemini-embedding-001"

# All source feed IDs the project knows about (id → human label).
FEED_CATALOG: dict[str, str] = {
    "arxiv_cs_ai": "arXiv cs.AI",
    "simonw": "Simon Willison's blog",
    "hf_papers": "Hugging Face daily papers",
    "hn": "Hacker News front page",
}

DEFAULT_USER_SETTINGS: dict = {
    "locale": "zh-TW",
    "routing": {
        "simple_model": MODEL_LITE,
        "complex_model": MODEL_FLASH,
        "downgrade_on_429": True,
    },
    "feeds": {fid: True for fid in FEED_CATALOG},
    # per-source keyword override (empty list → use global keywords.json)
    "feed_keywords": {fid: [] for fid in FEED_CATALOG},
}


# ---------- API key ----------
def get_api_key() -> str:
    return os.getenv("GOOGLE_API_KEY", "")


# ---------- Global keywords ----------
def load_keywords() -> list[str]:
    if not KEYWORDS_FILE.exists():
        KEYWORDS_FILE.write_text(json.dumps(
            ["LLM agents", "RAG", "LangGraph", "Gemini", "fine-tuning"],
            indent=2))
    return json.loads(KEYWORDS_FILE.read_text())


def save_keywords(keywords: list[str]) -> None:
    KEYWORDS_FILE.write_text(json.dumps(keywords, indent=2, ensure_ascii=False))


# ---------- User settings (routing + feeds + per-source keywords) ----------
def load_user_settings() -> dict:
    if not USER_SETTINGS_FILE.exists():
        save_user_settings(DEFAULT_USER_SETTINGS)
        return json.loads(json.dumps(DEFAULT_USER_SETTINGS))
    try:
        data = json.loads(USER_SETTINGS_FILE.read_text())
    except Exception:
        return json.loads(json.dumps(DEFAULT_USER_SETTINGS))
    # Merge to tolerate new fields added in code
    merged = json.loads(json.dumps(DEFAULT_USER_SETTINGS))
    for section, val in (data or {}).items():
        if isinstance(val, dict) and isinstance(merged.get(section), dict):
            merged[section].update(val)
        else:
            merged[section] = val
    # Heal: ensure every known feed has entries
    for fid in FEED_CATALOG:
        merged["feeds"].setdefault(fid, True)
        merged["feed_keywords"].setdefault(fid, [])
    return merged


def save_user_settings(settings: dict) -> None:
    USER_SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False))


def get_routing() -> dict:
    return load_user_settings().get("routing", DEFAULT_USER_SETTINGS["routing"])


def enabled_feeds() -> dict[str, bool]:
    return load_user_settings().get("feeds", {fid: True for fid in FEED_CATALOG})


def feed_keywords(feed_id: str) -> list[str]:
    return load_user_settings().get("feed_keywords", {}).get(feed_id, [])


def get_locale() -> str:
    locale = load_user_settings().get("locale", "zh-TW")
    return locale if locale in ("zh-TW", "en-US") else "zh-TW"


def set_locale(locale: str) -> None:
    data = load_user_settings()
    data["locale"] = locale if locale in ("zh-TW", "en-US") else "zh-TW"
    save_user_settings(data)
